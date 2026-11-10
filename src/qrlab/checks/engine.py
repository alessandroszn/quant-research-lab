"""Check registry, configuration loading and the engine.

The configuration must list **every** registered check, with ``enabled``, ``warning``,
``critical`` (a number or ``"none"``) and exactly the parameters the check declares. Unknown
checks, missing checks or parameters, and a critical level less severe than the warning level
raise. See ``configs/checks/example.toml`` (example values, not recommendations).
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from qrlab.checks import (
    concentration,
    costs,
    currency_drift,
    data_quality,
    diversification,
    etf_quality,
    risk,
)
from qrlab.checks.context import CheckContext
from qrlab.checks.framework import (
    CheckSpec,
    Direction,
    Finding,
    NotApplicable,
    Thresholds,
    classify,
)
from qrlab.core.errors import ValidationError

__all__ = ["ALL_CHECKS", "CheckConfig", "CheckResult", "load_check_config", "run_checks"]

ALL_CHECKS: tuple[CheckSpec, ...] = (
    *concentration.CHECKS,
    *diversification.CHECKS,
    *risk.CHECKS,
    *costs.CHECKS,
    *etf_quality.CHECKS,
    *currency_drift.CHECKS,
    *data_quality.CHECKS,
)
"""Every registered check, in report order."""

_BY_ID = {spec.id: spec for spec in ALL_CHECKS}
if len(_BY_ID) != len(ALL_CHECKS):  # pragma: no cover - guarded by tests
    raise RuntimeError("duplicated check ids")


@dataclass(frozen=True)
class CheckConfig:
    """Thresholds for every registered check, validated against the registry."""

    checks: Mapping[str, Thresholds]

    def __post_init__(self) -> None:
        """Validate ids, parameters and threshold ordering."""
        unknown = sorted(set(self.checks) - set(_BY_ID))
        missing = sorted(set(_BY_ID) - set(self.checks))
        if unknown:
            raise ValidationError(f"unknown checks in config: {unknown}")
        if missing:
            raise ValidationError(f"checks missing from config: {missing}")
        for check_id, thresholds in self.checks.items():
            spec = _BY_ID[check_id]
            if set(thresholds.params) != spec.params:
                expected = sorted(spec.params)
                raise ValidationError(
                    f"{check_id}: parameters {sorted(thresholds.params)} must be {expected}"
                )
            critical = thresholds.critical
            if critical is not None:
                less_severe = (
                    critical < thresholds.warning
                    if spec.direction is Direction.ABOVE
                    else critical > thresholds.warning
                )
                if less_severe:
                    raise ValidationError(f"{check_id}: critical level is less severe than warning")


@dataclass(frozen=True)
class CheckResult:
    """Findings, plus checks that passed, could not run, or were disabled, on ``as_of``."""

    as_of: date
    findings: tuple[Finding, ...]
    passed: tuple[str, ...]
    not_applicable: tuple[tuple[str, str], ...]
    disabled: tuple[str, ...]


def run_checks(context: CheckContext, config: CheckConfig) -> CheckResult:
    """Run every enabled check in registry order."""
    findings: list[Finding] = []
    passed: list[str] = []
    not_applicable: list[tuple[str, str]] = []
    disabled: list[str] = []
    for spec in ALL_CHECKS:
        thresholds = config.checks[spec.id]
        if not thresholds.enabled:
            disabled.append(spec.id)
            continue
        outcome = spec.run(context, thresholds.params)
        if isinstance(outcome, NotApplicable):
            not_applicable.append((spec.id, outcome.reason))
            continue
        triggered = False
        for measurement in outcome:
            verdict = classify(measurement.observed, thresholds, spec.direction)
            if verdict is None:
                continue
            triggered = True
            severity, threshold = verdict
            findings.append(
                Finding(
                    check_id=spec.id,
                    category=spec.category,
                    severity=severity,
                    subject=measurement.subject,
                    observed=measurement.observed,
                    threshold=threshold,
                    unit=spec.unit,
                    direction=spec.direction,
                    details=dict(measurement.details),
                )
            )
        if not triggered:
            passed.append(spec.id)
    return CheckResult(
        context.as_of,
        tuple(findings),
        tuple(passed),
        tuple(not_applicable),
        tuple(disabled),
    )


def load_check_config(path: Path) -> CheckConfig:
    """Load thresholds from a TOML file with one table per check (``[category.name]``)."""
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    checks: dict[str, Thresholds] = {}
    for category, tables in raw.items():
        if not isinstance(tables, dict):
            raise ValidationError(f"{category!r} must be a table of checks")
        for name, table in tables.items():
            check_id = f"{category}.{name}"
            if not isinstance(table, dict):
                raise ValidationError(f"{check_id} must be a table")
            checks[check_id] = _thresholds(check_id, table)
    return CheckConfig(checks)


def _thresholds(check_id: str, table: Mapping[str, object]) -> Thresholds:
    for key in ("enabled", "warning", "critical"):
        if key not in table:
            raise ValidationError(f"{check_id}: missing {key!r}")
    enabled, warning, critical = table["enabled"], table["warning"], table["critical"]
    if not isinstance(enabled, bool):
        raise ValidationError(f"{check_id}: enabled must be true or false")
    if isinstance(warning, bool) or not isinstance(warning, int | float):
        raise ValidationError(f"{check_id}: warning must be a number")
    if critical == "none":
        critical_value: float | None = None
    elif isinstance(critical, bool) or not isinstance(critical, int | float):
        raise ValidationError(f'{check_id}: critical must be a number or "none"')
    else:
        critical_value = float(critical)
    params = {k: v for k, v in table.items() if k not in {"enabled", "warning", "critical"}}
    return Thresholds(enabled, float(warning), critical_value, params)
