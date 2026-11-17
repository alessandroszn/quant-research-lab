"""Typed readers for ``[parameters]``: every value has a declared type, nothing is guessed."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

from qrlab.core.errors import ValidationError
from qrlab.data.provenance import Provenance
from qrlab.experiments.config import file_sha256, require_keys

__all__ = [
    "boolean",
    "choice",
    "day",
    "local_provenance",
    "loss_rules",
    "moment",
    "number",
    "table",
    "text",
    "whole",
]


def table(
    parent: Mapping[str, object], key: str, *, required: set[str], optional: set[str]
) -> Mapping[str, object]:
    """Return the sub-table ``key`` after checking its keys."""
    value = parent[key]
    if not isinstance(value, dict):
        raise ValidationError(f"{key} must be a table")
    require_keys(value, required=required, optional=optional, where=key)
    return value


def text(parent: Mapping[str, object], key: str) -> str:
    """Return non-empty text."""
    value = parent[key]
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} must be non-empty text")
    return value


def choice(parent: Mapping[str, object], key: str, options: set[str]) -> str:
    """Return one of ``options``."""
    value = text(parent, key)
    if value not in options:
        raise ValidationError(f"{key} must be one of {sorted(options)}, got {value!r}")
    return value


def number(parent: Mapping[str, object], key: str) -> float:
    """Return a finite number (int or float in TOML)."""
    value = parent[key]
    if type(value) not in (int, float) or not math.isfinite(float(value)):  # type: ignore[arg-type]
        raise ValidationError(f"{key} must be a finite number")
    return float(value)  # type: ignore[arg-type]


def whole(parent: Mapping[str, object], key: str, *, minimum: int) -> int:
    """Return an int of at least ``minimum``."""
    value = parent[key]
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{key} must be an int >= {minimum}")
    return value


def boolean(parent: Mapping[str, object], key: str) -> bool:
    """Return true or false."""
    value = parent[key]
    if not isinstance(value, bool):
        raise ValidationError(f"{key} must be true or false")
    return value


def day(parent: Mapping[str, object], key: str) -> date:
    """Return a TOML local date."""
    value = parent[key]
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValidationError(f"{key} must be a date (YYYY-MM-DD)")
    return value


def moment(parent: Mapping[str, object], key: str) -> datetime:
    """Return a TOML offset date-time (time zone required, for reproducible reports)."""
    value = parent[key]
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValidationError(
            f"{key} must be a date-time with a time zone, e.g. 2026-04-01T09:00:00Z"
        )
    return value


def local_provenance(path: Path, *, dataset: str) -> Provenance:
    """Provenance of a local input file; the modification time stands for the retrieval time."""
    stat = path.stat()
    return Provenance(
        source="user",
        dataset=dataset,
        url=f"file:{path.name}",
        retrieved_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        sha256=file_sha256(path),
        size_bytes=stat.st_size,
        terms="user-supplied file; stays in the git-ignored data folder",
    )


def loss_rules(
    parent: Mapping[str, object], *, where: str, fund_assets: bool
) -> tuple[int, frozenset[str]] | None:
    """Read an optional ``losses`` table (design note 11.5), or ``None`` when absent.

    It holds ``carry_years`` and, when ``fund_assets`` is true, the list of fund assets.
    """
    if "losses" not in parent:
        return None
    spec = parent["losses"]
    if not isinstance(spec, dict):
        raise ValidationError(f"{where} losses must be a table")
    keys = {"carry_years", "fund_assets"} if fund_assets else {"carry_years"}
    require_keys(spec, required=keys, optional=set(), where=f"{where} losses")
    carry = whole(spec, "carry_years", minimum=0)
    if not fund_assets:
        return carry, frozenset()
    names = spec["fund_assets"]
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValidationError(f"{where} losses: fund_assets must be a list of asset names")
    return carry, frozenset(names)
