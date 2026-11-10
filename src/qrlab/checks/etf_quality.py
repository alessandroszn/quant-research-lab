"""ETF-quality checks from master data (tracking difference and error: phase 2.5).

Shares are weights over the total portfolio value. Funds with an unknown value of the field
are left out of the measurement and counted in ``details["unknown_weight"]``; missing fields
are themselves reported by ``data_quality.missing_master``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from qrlab.checks.context import CheckContext
from qrlab.checks.framework import Direction, Measurement, MeasureUnit, NotApplicable, spec
from qrlab.core.errors import ValidationError
from qrlab.instruments.identifiers import validate_country
from qrlab.instruments.master import FUND_TYPES, Distribution, Instrument, Replication

__all__ = ["CHECKS"]

DAYS_PER_YEAR = 365.25


def _funds(ctx: CheckContext) -> list[tuple[Instrument, float]]:
    weights = ctx.position_weights()
    return [
        (ctx.instruments[isin], weight)
        for isin, weight in sorted(weights.items(), key=lambda item: item[0].code)
        if isin in ctx.instruments and ctx.instruments[isin].instrument_type in FUND_TYPES
    ]


def _share(
    ctx: CheckContext,
    value: Callable[[Instrument], object | None],
    flagged: Callable[[object], bool],
) -> list[Measurement] | NotApplicable:
    funds = _funds(ctx)
    if not funds:
        return NotApplicable("no funds with master data held")
    share = unknown = 0.0
    names = []
    for instrument, weight in funds:
        field = value(instrument)
        if field is None:
            unknown += weight
        elif flagged(field):
            share += weight
            names.append(instrument.isin.code)
    return [
        Measurement(
            "portfolio", share, {"funds": ", ".join(names), "unknown_weight": f"{unknown:.6f}"}
        )
    ]


def synthetic_share(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Weight of funds with synthetic replication."""
    return _share(ctx, lambda f: f.replication, lambda r: r is Replication.SYNTHETIC)


def domicile(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Weight of funds domiciled outside the ``preferred`` list of country codes."""
    preferred = params["preferred"]
    if not isinstance(preferred, list) or not preferred:
        raise ValidationError("etf_quality.domicile: preferred must be a non-empty list")
    allowed = {validate_country(code) for code in preferred}
    return _share(ctx, lambda f: f.domicile, lambda d: d not in allowed)


def distribution(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Weight of funds whose distribution policy differs from the ``preferred`` one."""
    try:
        preferred = Distribution(params["preferred"])
    except ValueError:
        raise ValidationError(
            "etf_quality.distribution: preferred must be accumulating or distributing"
        ) from None
    return _share(ctx, lambda f: f.distribution, lambda d: d is not preferred)


def fund_size(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Size of each fund in the base currency (one measurement per fund)."""
    measured = [
        Measurement(f.isin.code, float(ctx.to_base(f.fund_size, ctx.as_of).amount))
        for f, _ in _funds(ctx)
        if f.fund_size is not None
    ]
    return measured or NotApplicable("no fund size known")


def fund_age(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Age of each fund in years since inception (one measurement per fund)."""
    measured = [
        Measurement(f.isin.code, (ctx.as_of - f.inception).days / DAYS_PER_YEAR)
        for f, _ in _funds(ctx)
        if f.inception is not None
    ]
    return measured or NotApplicable("no inception date known")


CHECKS = (
    spec("etf_quality.synthetic_share", Direction.ABOVE, MeasureUnit.FRACTION, synthetic_share),
    spec("etf_quality.domicile", Direction.ABOVE, MeasureUnit.FRACTION, domicile, "preferred"),
    spec(
        "etf_quality.distribution", Direction.ABOVE, MeasureUnit.FRACTION, distribution, "preferred"
    ),
    spec("etf_quality.fund_size", Direction.BELOW, MeasureUnit.MONEY, fund_size),
    spec("etf_quality.fund_age", Direction.BELOW, MeasureUnit.YEARS, fund_age),
)
