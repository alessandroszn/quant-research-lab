"""Health-check framework: specifications, thresholds, measurements and findings.

A check *measures* one number per subject (the portfolio or an instrument). The engine then
compares the measurement with the user's thresholds in the check's fixed direction:

- ``ABOVE``: higher is worse; a finding when ``observed > warning`` (or ``> critical``);
- ``BELOW``: lower is worse; a finding when ``observed < warning`` (or ``< critical``).

Comparisons are strict: a value exactly at the threshold does not trigger. The direction is
part of the check's code, not of the config, so a configuration typo cannot invert a check.
Checks never change data and never give instructions: findings report numbers.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from qrlab.core.errors import ValidationError

if TYPE_CHECKING:
    from qrlab.checks.context import CheckContext

__all__ = [
    "Category",
    "CheckSpec",
    "Direction",
    "Finding",
    "MeasureUnit",
    "Measurement",
    "NotApplicable",
    "Severity",
    "Thresholds",
    "classify",
    "spec",
]


class Severity(Enum):
    """How serious a finding is."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Category(Enum):
    """Group of a check."""

    CONCENTRATION = "concentration"
    DIVERSIFICATION = "diversification"
    RISK = "risk"
    COSTS = "costs"
    ETF_QUALITY = "etf_quality"
    CURRENCY = "currency"
    DRIFT = "drift"
    DATA_QUALITY = "data_quality"


class Direction(Enum):
    """Which side of the threshold is worse."""

    ABOVE = "above"
    BELOW = "below"


class MeasureUnit(Enum):
    """Unit of a measurement, used for display."""

    FRACTION = "fraction"  # shown as a percentage
    RATIO = "ratio"  # plain number
    COUNT = "count"  # whole number
    MONEY = "money"  # amount in the base currency
    YEARS = "years"


@dataclass(frozen=True)
class Measurement:
    """One measured number for one subject (``"portfolio"`` or an ISIN code)."""

    subject: str
    observed: float
    details: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Refuse non-finite measurements: a check either measures a number or is N/A."""
        if not math.isfinite(self.observed):
            raise ValidationError(f"measurement for {self.subject} is not finite: {self.observed}")


@dataclass(frozen=True)
class NotApplicable:
    """The check cannot run with these inputs; the reason is reported, it never passes."""

    reason: str


Runner = Callable[["CheckContext", Mapping[str, object]], "list[Measurement] | NotApplicable"]


@dataclass(frozen=True)
class CheckSpec:
    """Definition of a check.

    Attributes
    ----------
    id
        ``"<category>.<name>"``, e.g. ``"concentration.largest_position"``.
    category, direction, unit
        Group, worse side and display unit.
    params
        Names of the extra parameters the check needs from the config.
    run
        Function of the context and parameters returning measurements or ``NotApplicable``.
    """

    id: str
    category: Category
    direction: Direction
    unit: MeasureUnit
    params: frozenset[str]
    run: Runner

    def __post_init__(self) -> None:
        """Require the id to start with the category."""
        if not self.id.startswith(self.category.value + "."):
            raise ValidationError(f"check id {self.id!r} must start with {self.category.value!r}.")


@dataclass(frozen=True)
class Thresholds:
    """User configuration of one check."""

    enabled: bool
    warning: float
    critical: float | None
    params: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    """A measurement that crossed a threshold."""

    check_id: str
    category: Category
    severity: Severity
    subject: str
    observed: float
    threshold: float
    unit: MeasureUnit
    direction: Direction
    details: Mapping[str, str]


def spec(
    check_id: str, direction: Direction, unit: MeasureUnit, run: Runner, *params: str
) -> CheckSpec:
    """Build a :class:`CheckSpec`, taking the category from the id prefix."""
    return CheckSpec(
        check_id, Category(check_id.split(".")[0]), direction, unit, frozenset(params), run
    )


def classify(
    observed: float, thresholds: Thresholds, direction: Direction
) -> tuple[Severity, float] | None:
    """Return the severity and the threshold crossed, or ``None`` (strict comparison)."""

    def worse(limit: float) -> bool:
        return observed > limit if direction is Direction.ABOVE else observed < limit

    if thresholds.critical is not None and worse(thresholds.critical):
        return Severity.CRITICAL, thresholds.critical
    if worse(thresholds.warning):
        return Severity.WARNING, thresholds.warning
    return None
