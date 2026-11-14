"""Experiment configs: one TOML file per analysis or study.

Tables: ``[experiment]`` (``name``, ``kind``, ``hypothesis``, and ``seed`` when the kind needs
one), ``[inputs]`` (local files, relative to the config file), ``[parameters]`` (kind-specific)
and ``[output]`` (``directory``). Unknown keys raise, so a typo is never ignored.

An input may be a **group**: a table of files with free keys, e.g. ``[inputs.holdings]`` with one
file per fund ISIN. Each file is flattened to the name ``<group>.<key>`` and is then checked,
hashed and recorded like any other input. Whether a name may be a group is the kind's decision
(:attr:`qrlab.experiments.ExperimentKind.input_groups`).

The **config hash** is the SHA-256 of the canonical JSON of every table except ``[output]``:
moving the results elsewhere is not a new configuration.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from qrlab.core.errors import ValidationError

__all__ = ["ExperimentConfig", "config_hash", "file_sha256", "load_config", "require_keys"]

_TABLES = {"experiment", "inputs", "parameters", "output"}


@dataclass(frozen=True)
class ExperimentConfig:
    """A parsed config (parameters still kind-specific and unvalidated)."""

    path: Path
    name: str
    kind: str
    hypothesis: str
    seed: int | None
    inputs: Mapping[str, Path]
    given_inputs: Mapping[str, str]
    parameters: Mapping[str, object]
    output_dir: Path
    raw: Mapping[str, object]
    hash: str
    input_groups: frozenset[str] = frozenset()
    """Names given as a table of files (their files are in ``inputs`` as ``<group>.<key>``)."""


def load_config(path: Path) -> ExperimentConfig:
    """Read and check the generic part of a config file."""
    path = Path(path)
    if not path.is_file():
        raise ValidationError(f"config file {path} does not exist")
    with path.open("rb") as handle:
        try:
            raw = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ValidationError(f"{path}: invalid TOML ({exc})") from exc
    require_keys(raw, required=_TABLES, optional=set(), where=str(path))
    for table in _TABLES:
        if not isinstance(raw[table], dict):
            raise ValidationError(f"[{table}] must be a table")
    experiment = raw["experiment"]
    require_keys(
        experiment, required={"name", "kind", "hypothesis"}, optional={"seed"}, where="[experiment]"
    )
    for key in ("name", "kind", "hypothesis"):
        if not isinstance(experiment[key], str) or not experiment[key].strip():
            raise ValidationError(f"[experiment] {key} must be non-empty text")
    seed = experiment.get("seed")
    if seed is not None and (type(seed) is not int or seed < 0):
        raise ValidationError("[experiment] seed must be an int >= 0")
    base = path.parent
    given = _flatten_inputs(raw["inputs"])
    inputs = {name: (base / value).resolve() for name, value in given.items()}
    groups = frozenset(name for name, value in raw["inputs"].items() if isinstance(value, dict))
    require_keys(raw["output"], required={"directory"}, optional=set(), where="[output]")
    directory = raw["output"]["directory"]
    if not isinstance(directory, str) or not directory.strip():
        raise ValidationError("[output] directory must be a path")
    return ExperimentConfig(
        path=path.resolve(),
        name=experiment["name"],
        kind=experiment["kind"],
        hypothesis=experiment["hypothesis"],
        seed=seed,
        inputs=inputs,
        given_inputs=given,
        parameters=raw["parameters"],
        output_dir=(base / directory).resolve(),
        raw=raw,
        hash=config_hash(raw),
        input_groups=groups,
    )


def _flatten_inputs(table: Mapping[str, object]) -> dict[str, str]:
    """Map every input name (``<group>.<key>`` inside a group) to its path as written."""
    given: dict[str, str] = {}
    for name, value in table.items():
        if isinstance(value, dict):
            if not value:
                raise ValidationError(f"[inputs] {name} has no files")
            for key, path in value.items():
                if not key.strip() or "." in key:
                    raise ValidationError(
                        f"[inputs] {name}: key {key!r} must be non-empty and contain no dot"
                    )
                given[f"{name}.{key}"] = _path(f"{name}.{key}", path)
        else:
            given[name] = _path(name, value)
    return given


def _path(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"[inputs] {name} must be a file path")
    return value


def config_hash(raw: Mapping[str, object]) -> str:
    """Return the SHA-256 of the config without its ``[output]`` table."""
    content = {k: v for k, v in raw.items() if k != "output"}
    canonical = json.dumps(content, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require_keys(
    table: Mapping[str, object], *, required: set[str], optional: set[str], where: str
) -> None:
    """Raise unless ``table`` has every required key and nothing unknown."""
    missing = sorted(required - set(table))
    unknown = sorted(set(table) - required - optional)
    if missing:
        raise ValidationError(f"{where}: missing {missing}")
    if unknown:
        raise ValidationError(f"{where}: unknown keys {unknown}")
