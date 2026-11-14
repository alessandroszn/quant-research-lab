"""Validate, hash, run, write: the single entry point used by scripts, the CLI and the app.

``run_experiment`` checks the config against its kind, hashes every input, runs the kind and
writes its tables (CSV), figures (PNG), report (HTML) and ``record.json`` into the output folder.
The record is written last, also when the run fails, so a folder without it is visibly
incomplete. Each run appends a line to ``trials.jsonl`` in the parent folder; the number of
configurations tried is the number of distinct config hashes recorded under the experiment's
name.

The record's ``code`` block says which code ran. From a source checkout the commit comes from
``git``; in a frozen (PyInstaller) program it comes from the ``build-info.json`` shipped next to
the executable, and ``git`` is never started.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import sys
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

import qrlab
from qrlab.core.errors import ValidationError
from qrlab.experiments.config import ExperimentConfig, file_sha256, load_config
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext

__all__ = [
    "RECORD_FORMAT",
    "RunResult",
    "configurations_tried",
    "count_trials",
    "run_experiment",
    "validate_experiment",
]

LEDGER = "trials.jsonl"
RECORD = "record.json"
BUILD_INFO = "build-info.json"
NOTICE = "NOTICE.txt"
RECORD_FORMAT = 1
"""Version of the ``record.json`` layout; it changes only with a major release (design 6.3a)."""
_PACKAGES = ("numpy", "pandas", "scipy", "statsmodels", "matplotlib")


@dataclass(frozen=True)
class RunResult:
    """Where a run wrote its outputs and how it ended."""

    output_dir: Path
    record: Mapping[str, Any]  # JSON-like: the content of record.json

    @property
    def succeeded(self) -> bool:
        """Return whether the run succeeded."""
        return bool(self.record["status"] == "success")


def validate_experiment(
    config_path: Path, *, kinds: Mapping[str, ExperimentKind]
) -> tuple[ExperimentConfig, ExperimentKind, object]:
    """Check a config, its kind, its parameters and its inputs without running anything."""
    config = load_config(config_path)
    if config.kind not in kinds:
        raise ValidationError(f"unknown experiment kind {config.kind!r}; known: {sorted(kinds)}")
    kind = kinds[config.kind]
    if not_groups := sorted(config.input_groups - set(kind.input_groups)):
        raise ValidationError(f"[inputs] for {kind.name}: {not_groups[0]} is not a group of files")
    plain = {name for name in config.inputs if name.split(".", 1)[0] not in config.input_groups}
    if not_tables := sorted(set(kind.input_groups) & plain):
        raise ValidationError(f"[inputs] for {kind.name}: {not_tables[0]} must be a table of files")
    missing = sorted(set(kind.inputs) - plain)
    unknown = sorted(plain - set(kind.inputs) - set(kind.optional_inputs))
    if missing or unknown:
        raise ValidationError(f"[inputs] for {kind.name}: missing {missing}, unknown {unknown}")
    for name, path in config.inputs.items():
        if not path.is_file():
            raise ValidationError(f"input {name}: {path} does not exist")
    if kind.needs_seed and config.seed is None:
        raise ValidationError(f"{kind.name} uses random numbers: [experiment] seed is required")
    if not kind.needs_seed and config.seed is not None:
        raise ValidationError(f"{kind.name} uses no random numbers: remove [experiment] seed")
    parameters = kind.parse(config.parameters)
    if kind.check_inputs is not None:
        kind.check_inputs(parameters, frozenset(config.inputs))
    return config, kind, parameters


def run_experiment(
    config_path: Path, *, kinds: Mapping[str, ExperimentKind], overwrite: bool
) -> RunResult:
    """Run one config; raise for config and input errors, record run failures."""
    config, kind, parameters = validate_experiment(config_path, kinds=kinds)
    code = _code_version()  # before writing anything: a broken build is refused up front
    out = config.output_dir
    if out.exists():
        if not overwrite:
            raise ValidationError(f"{out} exists; pass overwrite=True to replace it")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    hashes = {name: file_sha256(path) for name, path in config.inputs.items()}
    started = datetime.now(UTC)
    status, error = "success", None
    outputs: dict[str, object] = {}
    notice: str | None = None
    scalars: dict[str, object] = {}
    try:
        result = kind.run(RunContext(config, parameters, dict(config.inputs), config.seed))
        after = {name: file_sha256(path) for name, path in config.inputs.items()}
        if after != hashes:
            raise ValidationError("an input file changed during the run")
        outputs, scalars = _write_outputs(out, result)
        notice = result.notice
    except Exception as exc:
        status = "failure"
        error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    finished = datetime.now(UTC)
    tried = _append_trial(out.parent, config, status, finished)
    record: dict[str, object] = {
        "format": RECORD_FORMAT,
        "experiment": {"name": config.name, "kind": config.kind, "hypothesis": config.hypothesis},
        "config": {"path": str(config.path), "sha256": config.hash, "content": config.raw},
        "inputs": {
            name: {
                "given": config.given_inputs[name],
                "resolved": str(path),
                "sha256": hashes[name],
                "bytes": path.stat().st_size,
            }
            for name, path in config.inputs.items()
        },
        "seed": config.seed,
        "outputs": outputs,
        "notice": notice,
        "scalars": scalars,
        "configurations_tried": tried,
        "code": code,
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "status": status,
        "error": error,
    }
    (out / RECORD).write_text(
        json.dumps(record, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return RunResult(out, record)


def count_trials(ledger_dir: Path, name: str) -> int:
    """Return the number of distinct config hashes run under ``name``."""
    return len(_ledger_hashes(ledger_dir, name))


def configurations_tried(ledger_dir: Path, name: str, *, including: str) -> int:
    """Return the distinct config hashes run under ``name``, counting ``including`` as well.

    A kind calls this during its run, before the runner records the run in the ledger, to use
    the number of configurations tried (this one included) in a deflated Sharpe ratio.
    """
    return len(_ledger_hashes(ledger_dir, name) | {including})


def _ledger_hashes(ledger_dir: Path, name: str) -> set[str]:
    path = Path(ledger_dir) / LEDGER
    if not path.exists():
        return set()
    hashes = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry["name"] == name:
            hashes.add(str(entry["config_sha256"]))
    return hashes


def _write_outputs(
    out: Path, result: ExperimentOutput
) -> tuple[dict[str, object], dict[str, object]]:
    written: dict[str, object] = {}
    for name, item in sorted(result.tables.items()):
        if not isinstance(item.value, pd.DataFrame):
            raise ValidationError(f"table {name} must be a DataFrame")
        path = out / f"{name}.csv"
        item.value.to_csv(path, lineterminator="\n")
        written[path.name] = {"tag": item.tag, "sha256": file_sha256(path)}
    for name, png in sorted(result.figures.items()):
        path = out / f"{name}.png"
        path.write_bytes(png)
        written[path.name] = {"tag": "descriptive", "sha256": file_sha256(path)}
    if result.report_html is not None:
        path = out / "report.html"
        path.write_text(result.report_html, encoding="utf-8", newline="\n")
        written[path.name] = {"tag": "descriptive", "sha256": file_sha256(path)}
    if result.notice is not None:
        if not result.notice.strip():
            raise ValidationError("a notice must be non-empty text")
        path = out / NOTICE
        path.write_text(result.notice + "\n", encoding="utf-8", newline="\n")
        written[path.name] = {"tag": "descriptive", "sha256": file_sha256(path)}
    scalars: dict[str, object] = {}
    for name, item in sorted(result.scalars.items()):
        if isinstance(item.value, pd.DataFrame):
            raise ValidationError(f"scalar {name} must be a number or text")
        scalars[name] = {"value": item.value, "tag": item.tag}
    return written, scalars


def _append_trial(ledger_dir: Path, config: ExperimentConfig, status: str, when: datetime) -> int:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "name": config.name,
        "config_sha256": config.hash,
        "time": when.isoformat(),
        "status": status,
    }
    with (ledger_dir / LEDGER).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return count_trials(ledger_dir, config.name)


def _code_version() -> dict[str, object]:
    versions: dict[str, object] = {
        "qrlab": importlib.metadata.version("quant-research-lab"),
        "python": platform.python_version(),
        "packages": {name: importlib.metadata.version(name) for name in _PACKAGES},
    }
    if getattr(sys, "frozen", False):
        info = _build_info(Path(sys.executable).resolve().parent / BUILD_INFO)
        return {
            **versions,
            "frozen": True,
            "git_commit": info["commit"],
            "git_dirty": False,
            "built": info["built"],
        }
    source = Path(qrlab.__file__).resolve().parent
    commit, dirty = _git(source, "rev-parse", "HEAD"), _git(source, "status", "--porcelain")
    return {
        **versions,
        "frozen": False,
        "git_commit": commit,
        "git_dirty": None if dirty is None else bool(dirty),
    }


def _build_info(path: Path) -> dict[str, str]:
    """Read the commit and build time of a frozen program; anything incomplete raises."""
    if not path.is_file():
        raise ValidationError(f"no {BUILD_INFO} next to the program ({path}): broken build")
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(info, dict):
        raise ValidationError(f"{path} must hold a JSON object")
    commit = info.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValidationError(f"{path}: commit must be a 40-character git hash, got {commit!r}")
    if info.get("dirty") is not False:
        raise ValidationError(f"{path}: the build must come from a clean tree (dirty is false)")
    built = info.get("built")
    if not isinstance(built, str) or not built:
        raise ValidationError(f"{path}: built must be the build time")
    return {"commit": commit, "built": built}


def _git(cwd: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()
