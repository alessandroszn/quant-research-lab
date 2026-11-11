"""Checks that need fund holdings or tracking series (``CheckContext.lookthrough``).

Without look-through inputs every check here is not applicable, with the reason. Concentration
through holdings never counts the ``unknown``, ``unexplained``, ``not looked through`` or cash
buckets as one country, sector or issuer; their weights are listed in the details.
"""

from __future__ import annotations

from collections.abc import Mapping

from qrlab.checks.context import CheckContext
from qrlab.checks.framework import Direction, Measurement, MeasureUnit, NotApplicable, spec
from qrlab.core.errors import ValidationError
from qrlab.lookthrough.exposures import NOT_LOOKED_THROUGH, UNEXPLAINED, UNKNOWN, Dimension
from qrlab.lookthrough.inputs import LookThroughInputs
from qrlab.lookthrough.overlap import duplicated_exposure
from qrlab.lookthrough.tracking import TrackingDifference, td_vs_ter, tracking_difference
from qrlab.lookthrough.tracking import tracking_error as _tracking_error
from qrlab.metrics.errors import UndefinedMetricError

__all__ = ["CHECKS"]

_NO_LOOKTHROUGH = NotApplicable("no look-through inputs given")


def _inputs(ctx: CheckContext) -> LookThroughInputs | NotApplicable:
    return _NO_LOOKTHROUGH if ctx.lookthrough is None else ctx.lookthrough


def _largest(ctx: CheckContext, dimension: Dimension) -> list[Measurement] | NotApplicable:
    inputs = _inputs(ctx)
    if isinstance(inputs, NotApplicable):
        return inputs
    exposures = inputs.exposures
    found = exposures.largest(dimension)
    if found is None:
        return NotApplicable(f"no {dimension.value} known through holdings")
    name, weight = found
    details = {dimension.value: name}
    for bucket in (UNKNOWN, UNEXPLAINED, NOT_LOOKED_THROUGH):
        details[bucket] = f"{exposures.bucket(dimension, bucket):.6f}"
    if dimension is Dimension.ISSUER and not exposures.issuer_mapped:
        details["grouping"] = "security, not issuer (no issuer map)"
    return [Measurement("portfolio", weight, details)]


def country(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Largest country weight through holdings."""
    return _largest(ctx, Dimension.COUNTRY)


def sector(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Largest sector weight through holdings."""
    return _largest(ctx, Dimension.SECTOR)


def issuer(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Largest issuer weight (security weight without an issuer map)."""
    return _largest(ctx, Dimension.ISSUER)


def pair_overlap(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Overlap of every pair of funds looked through (one measurement per pair)."""
    inputs = _inputs(ctx)
    if isinstance(inputs, NotApplicable):
        return inputs
    pairs = inputs.overlaps()
    if not pairs:
        return NotApplicable("needs holdings of at least two funds")
    return [
        Measurement(
            f"{p.first.code} / {p.second.code}",
            p.overlap,
            {"unmatched": f"{p.unmatched_first:.6f} / {p.unmatched_second:.6f}"},
        )
        for p in pairs
    ]


def duplicated(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Weight of securities reached through two or more positions."""
    inputs = _inputs(ctx)
    if isinstance(inputs, NotApplicable):
        return inputs
    weight, isins = duplicated_exposure(inputs.exposures)
    return [Measurement("portfolio", weight, {"securities": str(len(isins))})]


def _tracked(ctx: CheckContext) -> list[tuple[str, TrackingDifference, float]] | NotApplicable:
    inputs = _inputs(ctx)
    if isinstance(inputs, NotApplicable):
        return inputs
    held = ctx.position_weights()
    found = []
    for isin, (fund, index) in sorted(inputs.tracking.items(), key=lambda item: item[0].code):
        if isin not in held:
            continue
        td = tracking_difference(fund, index)
        if td.annualised is not None:
            found.append((isin.code, td, td.annualised))
    if not found:
        return NotApplicable("no held fund has a year of tracking data")
    return found


def tracking_difference_check(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Annualised tracking difference per fund (negative: the fund lagged its index)."""
    tracked = _tracked(ctx)
    if isinstance(tracked, NotApplicable):
        return tracked
    return [
        Measurement(code, annualised, {"period": f"{td.start} - {td.end}"})
        for code, td, annualised in tracked
    ]


def tracking_error_check(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Annualised tracking error per fund."""
    inputs = _inputs(ctx)
    if isinstance(inputs, NotApplicable):
        return inputs
    periods = params["periods_per_year"]
    if isinstance(periods, bool) or not isinstance(periods, int | float):
        raise ValidationError("etf_quality.tracking_error: periods_per_year must be a number")
    held = ctx.position_weights()
    measured = []
    for isin, (fund, index) in sorted(inputs.tracking.items(), key=lambda item: item[0].code):
        if isin not in held:
            continue
        try:
            value = _tracking_error(fund, index, periods_per_year=float(periods))
        except UndefinedMetricError:
            continue
        measured.append(Measurement(isin.code, value))
    return measured or NotApplicable("no held fund has enough tracking data")


def ter_gap(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """TD + TER per fund: negative values are costs beyond the TER."""
    tracked = _tracked(ctx)
    if isinstance(tracked, NotApplicable):
        return tracked
    measured = []
    for code, _, annualised in tracked:
        instrument = next((f for i, f in ctx.instruments.items() if i.code == code), None)
        if instrument is None or instrument.ter is None:
            continue
        measured.append(
            Measurement(code, td_vs_ter(annualised, instrument.ter), {"ter": str(instrument.ter)})
        )
    return measured or NotApplicable("no tracked fund has a known TER")


def stale_holdings(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Count holdings snapshots older than ``max_age_days`` on ``as_of``."""
    inputs = _inputs(ctx)
    if isinstance(inputs, NotApplicable):
        return inputs
    limit = params["max_age_days"]
    if type(limit) is not int or limit < 0:
        raise ValidationError("data_quality.stale_holdings: max_age_days must be an int >= 0")
    stale = sorted(
        (isin.code, day)
        for isin, day in inputs.exposures.snapshot_dates.items()
        if (ctx.as_of - day).days > limit
    )
    details = {"funds": ", ".join(f"{code} ({day})" for code, day in stale)}
    return [Measurement("portfolio", float(len(stale)), details)]


LOOKTHROUGH_CHECKS = (
    spec("lookthrough.country", Direction.ABOVE, MeasureUnit.FRACTION, country),
    spec("lookthrough.sector", Direction.ABOVE, MeasureUnit.FRACTION, sector),
    spec("lookthrough.issuer", Direction.ABOVE, MeasureUnit.FRACTION, issuer),
    spec("lookthrough.pair_overlap", Direction.ABOVE, MeasureUnit.FRACTION, pair_overlap),
    spec("lookthrough.duplicated", Direction.ABOVE, MeasureUnit.FRACTION, duplicated),
)
TRACKING_CHECKS = (
    spec(
        "etf_quality.tracking_difference",
        Direction.BELOW,
        MeasureUnit.FRACTION,
        tracking_difference_check,
    ),
    spec(
        "etf_quality.tracking_error",
        Direction.ABOVE,
        MeasureUnit.FRACTION,
        tracking_error_check,
        "periods_per_year",
    ),
    spec("etf_quality.td_vs_ter", Direction.BELOW, MeasureUnit.FRACTION, ter_gap),
)
STALE_HOLDINGS = (
    spec(
        "data_quality.stale_holdings",
        Direction.ABOVE,
        MeasureUnit.COUNT,
        stale_holdings,
        "max_age_days",
    ),
)
CHECKS = LOOKTHROUGH_CHECKS + TRACKING_CHECKS + STALE_HOLDINGS
