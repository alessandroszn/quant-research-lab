"""Data-quality checks: carried-forward prices and FX rates, master data, P&L residual."""

from __future__ import annotations

from collections.abc import Mapping

from qrlab.checks.context import CheckContext
from qrlab.checks.framework import (
    Direction,
    Measurement,
    MeasureUnit,
    NotApplicable,
    spec,
)
from qrlab.core.errors import ValidationError
from qrlab.instruments.master import IssueKind, master_data_issues
from qrlab.portfolio.performance import pnl_breakdown

__all__ = ["CHECKS"]


def stale_prices(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Count prices carried forward from an earlier date on ``as_of``."""
    used = [
        (isin, day) for isin, requested, day in ctx.valuation.stale_prices if requested == ctx.as_of
    ]
    names = ", ".join(f"{isin.code} ({day.isoformat()})" for isin, day in used)
    return [Measurement("portfolio", float(len(used)), {"instruments": names})]


def stale_fx(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Count FX rates carried forward on ``as_of`` (if the converter records them)."""
    if not hasattr(ctx.to_base, "stale_uses"):
        return NotApplicable("the converter does not record carried-forward rates")
    uses = [(c, d) for c, requested, d in ctx.to_base.stale_uses if requested == ctx.as_of]
    names = ", ".join(f"{c.code} ({d.isoformat()})" for c, d in uses)
    return [Measurement("portfolio", float(len(uses)), {"currencies": names})]


def stale_master(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Count held instruments whose master data is older than ``max_age_days``."""
    max_age = params["max_age_days"]
    if type(max_age) is not int:
        raise ValidationError("data_quality.stale_master: max_age_days must be an int")
    held = [ctx.instruments[i] for i in ctx.position_weights() if i in ctx.instruments]
    stale = [
        i
        for i in master_data_issues(held, on=ctx.as_of, max_age_days=max_age)
        if i.kind is IssueKind.STALE
    ]
    return [
        Measurement(
            "portfolio", float(len(stale)), {"instruments": ", ".join(i.subject for i in stale)}
        )
    ]


def missing_master(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Count missing master-data fields, counting a held ISIN without any record as one."""
    held = list(ctx.position_weights())
    absent = [i.code for i in held if i not in ctx.instruments]
    records = [ctx.instruments[i] for i in held if i in ctx.instruments]
    missing = [
        f"{i.subject}:{i.field}"
        for i in master_data_issues(records, on=ctx.as_of, max_age_days=10**6)
        if i.kind is IssueKind.MISSING
    ]
    items = [f"{code}:record" for code in absent] + missing
    return [Measurement("portfolio", float(len(items)), {"missing": ", ".join(items)})]


def pnl_residual(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Absolute P&L residual from inception to ``as_of`` (should be zero)."""
    pnl = pnl_breakdown(ctx.history, ctx.valuation, ctx.to_base, start=None, end=ctx.as_of)
    return [Measurement("portfolio", abs(float(pnl.residual)), {"residual": str(pnl.residual)})]


CHECKS = (
    spec("data_quality.stale_prices", Direction.ABOVE, MeasureUnit.COUNT, stale_prices),
    spec("data_quality.stale_fx", Direction.ABOVE, MeasureUnit.COUNT, stale_fx),
    spec(
        "data_quality.stale_master",
        Direction.ABOVE,
        MeasureUnit.COUNT,
        stale_master,
        "max_age_days",
    ),
    spec("data_quality.missing_master", Direction.ABOVE, MeasureUnit.COUNT, missing_master),
    spec("data_quality.pnl_residual", Direction.ABOVE, MeasureUnit.MONEY, pnl_residual),
)
