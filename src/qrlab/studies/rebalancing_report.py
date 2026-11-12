"""HTML report of study 4 (rebalancing for a EUR ETF investor)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.reporting.formatting import Language, format_number, format_percent, style_for
from qrlab.reporting.html import Report, Section
from qrlab.reporting.tables import Table

__all__ = ["build_rebalancing_report"]

_STYLE = style_for(Language.EN)
_REFERENCES = (
    "Kenneth R. French Data Library (Developed market factors). European Central Bank: euro "
    "reference exchange rates and AAA euro-area yield curve (Svensson model).",
    "Daryanani, G. (2008), Opportunistic rebalancing: a new paradigm for wealth managers, "
    "Journal of Financial Planning 21(1).",
)


def build_rebalancing_report(
    *,
    title: str,
    hypothesis: str,
    facts: Sequence[tuple[str, str]],
    historical: pd.DataFrame,
    simulated: pd.DataFrame,
    comparison: pd.DataFrame,
    verdicts: pd.DataFrame,
) -> Report:
    """Assemble the report from the tables of :mod:`qrlab.studies.rebalancing`."""
    if historical.empty or simulated.empty:
        raise ValidationError("the report needs historical and simulated results")
    sections = [_verdicts_section(verdicts)]
    for scenario in historical["scenario"].unique():
        sections.append(
            _outcomes_section(
                f"Historical path, {scenario} costs",
                historical[historical["scenario"] == scenario],
                "One path: the actual monthly returns. Descriptive, not a forecast.",
            )
        )
    for scenario in simulated["scenario"].unique():
        sections.append(
            _outcomes_section(
                f"Simulated paths, {scenario} costs (medians)",
                simulated[simulated["scenario"] == scenario],
                "Medians across stationary-bootstrap paths of the same history; after-tax "
                "wealth also shows the 5th and 95th percentiles.",
            )
        )
    sections.append(_comparison_section(comparison))
    return Report(
        title=title,
        language=Language.EN,
        facts=(("Hypothesis", hypothesis), *facts),
        warnings=(
            "Proxies, not funds: index and constructed-bond returns without fund fees.",
            "Simulated paths resample one history (one regime of rates and markets); they are "
            "scenarios under stated assumptions, not forecasts.",
            "Tax simplified: one rate on realised gains, no offset of losses, liquidation at the "
            "end; reduced bond rate and stamp duty ignored. Not tax advice.",
        ),
        sections=tuple(sections),
        footer=("Research analytics, not investment or tax advice.", *_REFERENCES),
    )


def _outcomes_section(title: str, frame: pd.DataFrame, note: str) -> Section:
    has_range = "after_tax_wealth_p05" in frame.columns
    rows = []
    for _, row in frame.iterrows():
        wealth = _eur(row["after_tax_wealth"])
        if has_range:
            wealth += f" [{_eur(row['after_tax_wealth_p05'])}, {_eur(row['after_tax_wealth_p95'])}]"
        rows.append(
            (
                str(row["policy"]),
                wealth,
                _pct(row["after_tax_return"]),
                _pct(row["volatility"]),
                _pct(row["max_drawdown"]),
                _pct(row["mean_abs_deviation"]),
                _pct(row["final_equity_weight"]),
                _pct(row["annual_turnover"]),
                _eur(row["costs"]),
                _eur(row["taxes"]),
                _eur(row["deferred_tax"]),
            )
        )
    table = Table(
        title=title,
        columns=(
            "Policy",
            "After-tax wealth (EUR)",
            "After-tax return p.a.",
            "Volatility p.a.",
            "Max drawdown",
            "Mean |equity - target|",
            "Final equity weight",
            "Turnover p.a.",
            "Costs (EUR)",
            "Taxes paid (EUR)",
            "Tax at liquidation (EUR)",
        ),
        rows=tuple(rows),
        align=("left", *("right",) * 10),
        notes=(note,),
    )
    return Section(title=title, paragraphs=(), tables=(table,), figures=())


def _comparison_section(frame: pd.DataFrame) -> Section:
    rows = tuple(
        (
            str(row["scenario"]),
            str(row["policy"]),
            f"{_eur(row['after_tax_wealth_median'])} [{_eur(row['after_tax_wealth_p05'])}, "
            f"{_eur(row['after_tax_wealth_p95'])}]",
            _pct(row["share_wealth_higher"]),
            _pct(row["mean_abs_deviation_median"]),
            _eur(row["costs_and_taxes_median"]),
            _pct(row["volatility_median"]),
        )
        for _, row in frame.iterrows()
    )
    table = Table(
        title="Paired differences against the reference policy",
        columns=(
            "Costs",
            "Policy",
            "After-tax wealth difference, median [5 %, 95 %]",
            "Paths with more wealth",
            "Deviation difference",
            "Costs + taxes difference (EUR)",
            "Volatility difference",
        ),
        rows=rows,
        align=("left", "left", *("right",) * 5),
        notes=("Policy minus reference on the same simulated paths.",),
    )
    return Section(title="Against the reference", paragraphs=(), tables=(table,), figures=())


def _verdicts_section(frame: pd.DataFrame) -> Section:
    rows = tuple(
        (
            str(row["scenario"]),
            str(row["hypothesis"]),
            str(row["condition"]),
            _pct(row["share"]),
            "yes" if bool(row["supported"]) else "no",
        )
        for _, row in frame.iterrows()
    )
    table = Table(
        title="Hypotheses: share of simulated paths where each stated direction holds",
        columns=("Costs", "Hypothesis", "Condition", "Share of paths", "Supported"),
        rows=rows,
        align=("left", "left", "left", "right", "left"),
        notes=(
            "Supported when every condition of the hypothesis holds in at least the share fixed "
            "in the design note (a summary rule, not a significance test).",
        ),
    )
    return Section(title="Hypotheses", paragraphs=(), tables=(table,), figures=())


def _eur(value: object) -> str:
    number = float(value)  # type: ignore[arg-type]
    return format_number(number, 0, style=_STYLE) if math.isfinite(number) else "n/a"


def _pct(value: object) -> str:
    number = float(value)  # type: ignore[arg-type]
    return format_percent(number, 2, style=_STYLE) if math.isfinite(number) else "n/a"
