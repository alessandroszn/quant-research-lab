"""Scenario definitions and their TOML files (``configs/scenarios/``).

A file holds one table per scenario, keyed by a short id::

    [gfc_2008]
    kind = "historical"
    description = "Global financial crisis, S&P 500 peak to trough"
    start = 2007-10-09
    end = 2009-03-09

    [market_minus_30]
    kind = "hypothetical"
    description = "Equity market falls 30 %"
    factors = { "Mkt-RF" = -0.30 }
    positions = {}
    currencies = { USD = -0.10 }

Historical scenarios cover returns dated in ``(start, end]``. Hypothetical shocks are simple
returns above -1; every table of a hypothetical scenario is required (it may be empty).
"""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.instruments.identifiers import Isin

__all__ = ["HistoricalScenario", "HypotheticalScenario", "Scenario", "load_scenarios"]


@dataclass(frozen=True)
class HistoricalScenario:
    """Replay of the returns dated in ``(start, end]``."""

    id: str
    description: str
    start: date
    end: date

    def __post_init__(self) -> None:
        """Validate the window."""
        _require_text(self.id, "id")
        _require_text(self.description, f"{self.id}: description")
        if not (_is_date(self.start) and _is_date(self.end)):
            raise ValidationError(f"{self.id}: start and end must be dates")
        if self.end <= self.start:
            raise ValidationError(f"{self.id}: end {self.end} is not after start {self.start}")


@dataclass(frozen=True)
class HypotheticalScenario:
    """Explicit shocks (simple returns) to factors, positions and currencies."""

    id: str
    description: str
    factors: Mapping[str, float]
    positions: Mapping[Isin, float]
    currencies: Mapping[Currency, float]

    def __post_init__(self) -> None:
        """Validate the shocks."""
        _require_text(self.id, "id")
        _require_text(self.description, f"{self.id}: description")
        for kind, shocks in (
            ("factor", self.factors),
            ("position", self.positions),
            ("currency", self.currencies),
        ):
            for key, value in shocks.items():
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise ValidationError(f"{self.id}: {kind} shock {key} must be a number")
                if not math.isfinite(value) or value <= -1.0:
                    raise ValidationError(f"{self.id}: {kind} shock {key} must be above -1")


Scenario = HistoricalScenario | HypotheticalScenario


def load_scenarios(path: Path) -> tuple[Scenario, ...]:
    """Load scenario definitions from a TOML file, in file order."""
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    scenarios: list[Scenario] = []
    for scenario_id, table in raw.items():
        if not isinstance(table, dict):
            raise ValidationError(f"scenario {scenario_id!r} must be a table")
        kind = table.get("kind")
        if kind == "historical":
            _require_keys(scenario_id, table, {"kind", "description", "start", "end"})
            scenarios.append(
                HistoricalScenario(scenario_id, table["description"], table["start"], table["end"])
            )
        elif kind == "hypothetical":
            keys = {"kind", "description", "factors", "positions", "currencies"}
            _require_keys(scenario_id, table, keys)
            for name in ("factors", "positions", "currencies"):
                if not isinstance(table[name], dict):
                    raise ValidationError(f"{scenario_id}: {name} must be a table")
            scenarios.append(
                HypotheticalScenario(
                    scenario_id,
                    table["description"],
                    dict(table["factors"]),
                    {Isin(code): v for code, v in table["positions"].items()},
                    {Currency(code): v for code, v in table["currencies"].items()},
                )
            )
        else:
            raise ValidationError(f'{scenario_id}: kind must be "historical" or "hypothetical"')
    ids = [s.id for s in scenarios]
    if not ids:
        raise ValidationError(f"no scenarios in {path}")
    return tuple(scenarios)


def _require_keys(scenario_id: str, table: Mapping[str, object], keys: set[str]) -> None:
    if set(table) != keys:
        raise ValidationError(f"{scenario_id}: keys {sorted(table)} must be exactly {sorted(keys)}")


def _is_date(value: object) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be non-empty text")
