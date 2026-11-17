"""Read-only queries on a workspace folder, shared by the desktop app and the CLI.

A workspace is a folder with ``configs/`` (experiment TOML files), ``data/`` (git-ignored: user
files and the raw store under ``data/raw``), ``portfolios/`` (one folder per portfolio described
in the app, phase 8.8) and ``results/`` (run outputs with ``record.json``).
Nothing here computes or changes anything: it lists configs with their validation status, the
runs that were recorded, and the raw files with their provenance.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from qrlab.core.errors import QrlabError, ValidationError
from qrlab.data.store import RawStore
from qrlab.experiments.config import load_config
from qrlab.experiments.registry import ExperimentKind
from qrlab.experiments.runner import RECORD, validate_experiment

__all__ = [
    "WORKSPACE_FOLDERS",
    "ConfigEntry",
    "RawFileEntry",
    "RunEntry",
    "config_template",
    "create_workspace",
    "list_configs",
    "list_raw_files",
    "list_runs",
]

WORKSPACE_FOLDERS = ("configs", "data", "portfolios", "results")

_CONFIG_ERRORS = (QrlabError, tomllib.TOMLDecodeError, OSError, ValueError, KeyError, TypeError)


@dataclass(frozen=True)
class ConfigEntry:
    """A config file, its kind (if readable) and whether it validates."""

    path: Path
    name: str | None
    kind: str | None
    valid: bool
    error: str | None


@dataclass(frozen=True)
class RunEntry:
    """A recorded run (one ``record.json``)."""

    output_dir: Path
    name: str
    kind: str
    status: str
    started: str
    finished: str
    config_sha256: str
    configurations_tried: int
    error: str | None


@dataclass(frozen=True)
class RawFileEntry:
    """A raw-store file with its provenance."""

    path: Path
    source: str
    dataset: str
    url: str
    retrieved_at: datetime
    size_bytes: int
    sha256: str
    terms: str
    latest: bool
    age_days: int


def create_workspace(root: Path) -> Path:
    """Create the :data:`WORKSPACE_FOLDERS` under ``root`` (existing ones are kept)."""
    folder = Path(root)
    if folder.exists() and not folder.is_dir():
        raise QrlabError(f"{folder} is a file, not a folder")
    for name in WORKSPACE_FOLDERS:
        (folder / name).mkdir(parents=True, exist_ok=True)
    return folder


def list_configs(root: Path, *, kinds: Mapping[str, ExperimentKind]) -> list[ConfigEntry]:
    """Every ``*.toml`` under ``configs/``, sorted by path, with its validation result."""
    folder = Path(root) / "configs"
    entries = []
    for path in sorted(folder.rglob("*.toml")) if folder.is_dir() else []:
        name = kind = None
        try:
            config = load_config(path)
            name, kind = config.name, config.kind
        except _CONFIG_ERRORS:
            pass
        try:
            validate_experiment(path, kinds=kinds)
        except _CONFIG_ERRORS as exc:
            entries.append(ConfigEntry(path, name, kind, False, f"{type(exc).__name__}: {exc}"))
            continue
        entries.append(ConfigEntry(path, name, kind, True, None))
    return entries


def list_runs(root: Path) -> list[RunEntry]:
    """Every ``record.json`` under ``results/``, newest finished first.

    Unreadable records are skipped: a folder without a valid record is an incomplete run.
    Folders whose name starts with a dot are skipped too: they are a run's staging folder or
    the earlier outputs it is replacing (design note 12.2).
    """
    folder = Path(root) / "results"
    runs = []
    for record_path in folder.rglob(RECORD) if folder.is_dir() else []:
        if any(part.startswith(".") for part in record_path.relative_to(folder).parts[:-1]):
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            runs.append(
                RunEntry(
                    output_dir=record_path.parent,
                    name=str(record["experiment"]["name"]),
                    kind=str(record["experiment"]["kind"]),
                    status=str(record["status"]),
                    started=str(record["started"]),
                    finished=str(record["finished"]),
                    config_sha256=str(record["config"]["sha256"]),
                    configurations_tried=int(record["configurations_tried"]),
                    error=None if record["error"] is None else str(record["error"]),
                )
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(runs, key=lambda r: (r.finished, str(r.output_dir)), reverse=True)


def list_raw_files(root: Path, *, now: datetime) -> list[RawFileEntry]:
    """Every raw-store vintage under ``data/raw``, by source and dataset, oldest first.

    ``now`` must be timezone-aware; the age is in whole days.
    """
    if now.utcoffset() is None:
        raise QrlabError("now must be timezone-aware")
    raw = Path(root) / "data" / "raw"
    store = RawStore(Path(root) / "data")
    entries = []
    sources = sorted(p for p in raw.iterdir() if p.is_dir()) if raw.is_dir() else []
    for source in sources:
        for dataset in sorted(p for p in source.iterdir() if p.is_dir()):
            vintages = store.vintages(source.name, dataset.name)
            for position, stored in enumerate(vintages):
                p = stored.provenance
                entries.append(
                    RawFileEntry(
                        path=stored.path,
                        source=p.source,
                        dataset=p.dataset,
                        url=p.url,
                        retrieved_at=p.retrieved_at,
                        size_bytes=p.size_bytes,
                        sha256=p.sha256,
                        terms=p.terms,
                        latest=position == len(vintages) - 1,
                        age_days=(now - p.retrieved_at).days,
                    )
                )
    return entries


def config_template(
    kind: ExperimentKind,
    *,
    inputs: Mapping[str, str] | None = None,
    parameters: Mapping[str, str] | None = None,
) -> str:
    """Return a skeleton config for ``kind``: every required key, values left to fill in.

    ``inputs`` (paths, relative to the config) and ``parameters`` (TOML values, e.g.
    ``'"native"'``) are written filled in instead (phase 8.8); their names must be the kind's.
    """
    given_inputs = dict(inputs or {})
    given = dict(parameters or {})
    unknown = sorted(set(given_inputs) - set(kind.inputs) - set(kind.optional_inputs))
    if unknown:
        raise ValidationError(f"unknown inputs {unknown} for {kind.name}")
    unknown = sorted(set(given) - set(kind.parameters) - set(kind.optional_parameters))
    if unknown:
        raise ValidationError(f"unknown parameters {unknown} for {kind.name}")

    def input_line(name: str, optional: bool) -> str:
        if name in given_inputs:
            return f"{name} = {json.dumps(given_inputs[name])}"
        return (
            f'# {name} = "../data/FILL-IN"  # optional'
            if optional
            else (f'{name} = "../data/FILL-IN"')
        )

    def parameter_line(name: str, optional: bool) -> str:
        if name in given:
            return f"{name} = {given[name]}"
        return f"# {name} = FILL-IN" + ("  # optional" if optional else "")

    lines = [
        f"# New {kind.name} experiment: {kind.description}.",
        "# Fill in every value, then Validate. Paths are relative to this file.",
        "",
        "[experiment]",
        'name = "my-experiment"',
        f'kind = "{kind.name}"',
        'hypothesis = "State the question before running"',
    ]
    if kind.needs_seed:
        lines.append("seed = 1")
    lines += ["", "[inputs]"]
    lines += [input_line(name, False) for name in kind.inputs]
    lines += [input_line(name, True) for name in kind.optional_inputs]
    for group in kind.input_groups:
        lines += [
            "",
            f"# [inputs.{group}]  # optional group: one file per key",
            '# KEY = "../data/FILL-IN"',
        ]
    lines += ["", "[parameters]"]
    lines += [parameter_line(name, False) for name in kind.parameters]
    lines += [parameter_line(name, True) for name in kind.optional_parameters]
    lines += ["", "[output]", 'directory = "../results/my-experiment"', ""]
    return "\n".join(lines)
