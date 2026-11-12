"""HTML report of study 2 (1/N against optimised portfolios), all results out of sample."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.metrics.sharpe_inference import ProbabilisticSharpe
from qrlab.reporting.formatting import Language, format_number, format_percent, style_for
from qrlab.reporting.html import Report, Section
from qrlab.reporting.tables import Table

__all__ = ["build_one_over_n_report"]

_STYLE = style_for(Language.EN)
_KEYS = ["dataset", "window", "cost_per_unit"]
_REFERENCES = (
    "DeMiguel, V., Garlappi, L. and Uppal, R. (2009), Optimal versus naive diversification: "
    "how inefficient is the 1/N portfolio strategy?, Review of Financial Studies 22(5).",
    "Ledoit, O. and Wolf, M. (2004), A well-conditioned estimator for large-dimensional "
    "covariance matrices, Journal of Multivariate Analysis 88(2).",
    "Lopez de Prado, M. (2016), Building diversified portfolios that outperform out of sample, "
    "Journal of Portfolio Management 42(4).",
    "Black, F. and Litterman, R. (1992), Global portfolio optimization, Financial Analysts "
    "Journal 48(5).",
)


def build_one_over_n_report(
    *,
    title: str,
    hypothesis: str,
    facts: Sequence[tuple[str, str]],
    performance: pd.DataFrame,
    comparisons: pd.DataFrame,
    pairs: pd.DataFrame | None,
    deflated: tuple[str, ProbabilisticSharpe, int] | None,
    significance: float,
) -> Report:
    """Assemble the report from the tables of :mod:`qrlab.studies.one_over_n`."""
    if performance.empty or comparisons.empty:
        raise ValidationError("the report needs performance and comparison tables")
    sections = []
    for key, group in performance.groupby(_KEYS, sort=False):
        mask = (comparisons[_KEYS] == pd.Series(key, index=_KEYS)).all(axis=1)
        sections.append(_group_section(group, comparisons.loc[mask], significance))
    if pairs is not None and not pairs.empty:
        sections.append(_pairs_section(pairs, significance))
    sections.append(_selection_section(deflated))
    return Report(
        title=title,
        language=Language.EN,
        facts=(("Hypothesis", hypothesis), *facts),
        warnings=(
            "All results are out of sample: each decision uses only the months before it, and "
            "trades execute one trading day later.",
            "Statistical significance is not economic significance; not rejecting a hypothesis "
            "is not evidence that there is no effect.",
        ),
        sections=tuple(sections),
        footer=("Research analytics, not investment advice.", *_REFERENCES),
    )


def _group_section(perf: pd.DataFrame, tests: pd.DataFrame, significance: float) -> Section:
    first = perf.iloc[0]
    label = (
        f"{first['dataset']}, window {int(first['window'])} months, "
        f"cost {_num(float(first['cost_per_unit']) * 1e4, 0)} bp"
    )
    by_strategy = tests.set_index("strategy")
    rows = []
    for _, row in perf.iterrows():
        name = str(row["strategy"])
        test = by_strategy.loc[name] if name in by_strategy.index else None
        rows.append(
            (
                name,
                _num(row["sharpe"]),
                _pct(row["ceq"]),
                _pct(row["mean"]),
                _pct(row["volatility"]),
                _pct(row["turnover"]),
                _pct(row["max_drawdown"]),
                "" if test is None else _num(test["z_hac"]),
                "" if test is None else _num(test["holm"], 4),
                ""
                if test is None
                else f"{_pct(test['ceq_difference_annual'])} "
                f"[{_pct(test['ceq_low_annual'])}, {_pct(test['ceq_high_annual'])}]",
                str(int(row["fallbacks"])),
            )
        )
    table = Table(
        title=f"Net performance and tests against 1/N ({label})",
        columns=(
            "Strategy",
            "Sharpe p.a.",
            "CEQ p.a.",
            "Mean p.a.",
            "Volatility p.a.",
            "Turnover / month",
            "Max drawdown",
            "z vs 1/N (HAC)",
            "p Holm",
            "CEQ difference p.a. [bootstrap]",
            "Fallback months",
        ),
        rows=tuple(rows),
        align=("left", *("right",) * 10),
        notes=(
            f"Months {first['start']} to {first['end']} (N = {int(first['n'])}). Ledoit-Wolf "
            f"HAC test of the Sharpe-ratio difference against 1/N; Holm across strategies at "
            f"{_num(significance, 2)}.",
        ),
    )
    return Section(title=label, paragraphs=(), tables=(table,), figures=())


def _pairs_section(pairs: pd.DataFrame, significance: float) -> Section:
    rows = tuple(
        (
            str(row["dataset"]),
            str(int(row["window"])),
            _num(float(row["cost_per_unit"]) * 1e4, 0),
            f"{row['robust']} vs {row['sample']}",
            _num(row["difference_per_month"], 3),
            _num(row["z_hac"]),
            _num(row["pvalue_hac"], 4),
            _num(row["holm"], 4),
        )
        for _, row in pairs.iterrows()
    )
    table = Table(
        title="Robust against sample estimates (H2)",
        columns=(
            "Dataset",
            "Window",
            "Cost bp",
            "Pair",
            "Sharpe difference / month",
            "z (HAC)",
            "p",
            "p Holm",
        ),
        rows=rows,
        align=("left", "right", "right", "left", *("right",) * 4),
        notes=(f"Holm across the pairs of each dataset, window and cost at {significance:g}.",),
    )
    return Section(title="Robust estimation (H2)", paragraphs=(), tables=(table,), figures=())


def _selection_section(deflated: tuple[str, ProbabilisticSharpe, int] | None) -> Section:
    if deflated is None:
        text = "Deflated Sharpe ratio not computed: fewer than two variants were evaluated."
        return Section("Selection across variants", (text,), (), ())
    label, dsr, n_trials = deflated
    return Section(
        title="Selection across variants",
        paragraphs=(
            f"Best variant by net Sharpe ratio: {label}. Deflated Sharpe ratio "
            f"{_num(dsr.probability, 3)} with {n_trials} trials (variants in this run times the "
            "configurations recorded in the trial ledger); it tests against zero, not against "
            "1/N.",
        ),
        tables=(),
        figures=(),
    )


def _num(value: object, decimals: int = 2) -> str:
    number = float(value)  # type: ignore[arg-type]
    return format_number(number, decimals, style=_STYLE) if math.isfinite(number) else "n/a"


def _pct(value: object) -> str:
    number = float(value)  # type: ignore[arg-type]
    return format_percent(number, 2, style=_STYLE) if math.isfinite(number) else "n/a"
