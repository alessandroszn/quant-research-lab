"""Helpers shared by the study kinds: list parameters and Ken French input provenance."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from qrlab.core.errors import ValidationError
from qrlab.data.errors import IntegrityError
from qrlab.data.ken_french import SOURCE, TERMS
from qrlab.data.provenance import Provenance
from qrlab.experiments.config import file_sha256
from qrlab.experiments.kinds._params import number, table, whole
from qrlab.studies.volatility_managed import BootstrapSettings

__all__ = [
    "bootstrap_settings",
    "describe",
    "ken_french_provenance",
    "names",
    "numbers",
    "raw_provenance",
]

_SIDECAR = ".provenance.json"


def names(parent: Mapping[str, object], key: str) -> tuple[str, ...]:
    """Return a non-empty list of distinct names."""
    value = parent[key]
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise ValidationError(f"{key} must be a non-empty list of names")
    if len(set(value)) != len(value):
        raise ValidationError(f"{key} has duplicates")
    return tuple(value)


def numbers(parent: Mapping[str, object], key: str, *, allow_inf: bool) -> tuple[float, ...]:
    """Return a non-empty list of distinct numbers (``inf`` only when allowed)."""
    value = parent[key]
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{key} must be a non-empty list of numbers")
    out = []
    for item in value:
        if (
            type(item) not in (int, float)
            or math.isnan(item)
            or (math.isinf(item) and not allow_inf)
        ):
            raise ValidationError(f"{key} must contain numbers{' or inf' if allow_inf else ''}")
        out.append(float(item))
    if len(set(out)) != len(out):
        raise ValidationError(f"{key} has duplicates")
    return tuple(out)


def bootstrap_settings(parameters: Mapping[str, object]) -> BootstrapSettings:
    """Read ``bootstrap = {mean_block_length, n_resamples, confidence}``."""
    boot = table(
        parameters,
        "bootstrap",
        required={"mean_block_length", "n_resamples", "confidence"},
        optional=set(),
    )
    return BootstrapSettings(
        mean_block_length=number(boot, "mean_block_length"),
        n_resamples=whole(boot, "n_resamples", minimum=1),
        confidence=number(boot, "confidence"),
    )


def ken_french_provenance(path: Path, dataset: str) -> Provenance:
    """Provenance of a Ken French input (see :func:`raw_provenance`)."""
    return raw_provenance(path, source=SOURCE, dataset=dataset, terms=TERMS)


def raw_provenance(path: Path, *, source: str, dataset: str, terms: str) -> Provenance:
    """Provenance from the raw store's sidecar when present, else from the local file.

    A sidecar must match the file's SHA-256 and name the expected source and dataset.
    """
    sidecar = path.with_name(path.name + _SIDECAR)
    sha = file_sha256(path)
    if sidecar.is_file():
        stored = Provenance.from_json(sidecar.read_text(encoding="utf-8"))
        if stored.sha256 != sha:
            raise IntegrityError(f"{path.name}: SHA-256 differs from its provenance sidecar")
        if stored.source != source or stored.dataset != dataset:
            raise ValidationError(
                f"{path.name}: provenance says {stored.source}/{stored.dataset}, "
                f"expected {source}/{dataset}"
            )
        return stored
    stat = path.stat()
    return Provenance(
        source=source,
        dataset=dataset,
        url=f"file:{path.name}",
        retrieved_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        sha256=sha,
        size_bytes=stat.st_size,
        terms=terms,
    )


def describe(provenance: Provenance) -> str:
    """One line for a report: dataset, origin, retrieval date and hash prefix."""
    return (
        f"{provenance.dataset}: {provenance.url}, retrieved "
        f"{provenance.retrieved_at.date().isoformat()}, SHA-256 {provenance.sha256[:12]}"
    )
