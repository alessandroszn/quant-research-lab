"""HTML report of study 1 (volatility-managed factors): in and out of sample kept apart."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.metrics.sharpe_inference import ProbabilisticSharpe
from qrlab.reporting.formatting import Language, format_number, format_percent, style_for
from qrlab.reporting.html import Report, Section
from qrlab.reporting.tables import Table

__all__ = ["build_volatility_managed_report"]

_STYLE = style_for(Language.EN)
_DISCLAIMER = "Research analytics, not investment advice."
_REFERENCES = (
    "Moreira, A. and Muir, T. (2017), Volatility-Managed Portfolios, Journal of Finance 72(4).",
    "Cederburg, S., O'Doherty, M. S., Wang, F. and Yan, X. (2020), On the performance of "
    "volatility-managed portfolios, Journal of Financial Economics 138(1).",
)


def build_volatility_managed_report(
    *,
    title: str,
    hypothesis: str,
    facts: Sequence[tuple[str, str]],
    in_sample: pd.DataFrame,
    out_of_sample: pd.DataFrame,
    deflated: tuple[str, ProbabilisticSharpe, int] | None,
    significance: float,
) -> Report:
    """Assemble the report from the tables of :mod:`qrlab.studies.volatility_managed`."""
    if in_sample.empty or out_of_sample.empty:
        raise ValidationError("the report needs in-sample and out-of-sample results")
    sections = [_in_sample_section(in_sample, significance)]
    for _, group in out_of_sample.groupby(["cap", "cost_per_unit"], sort=False):
        cap, cost = float(group["cap"].iloc[0]), float(group["cost_per_unit"].iloc[0])
        sections.append(_out_of_sample_section(group, cap, cost, significance))
    sections.append(_selection_section(deflated))
    return Report(
        title=title,
        language=Language.EN,
        facts=(("Hypothesis", hypothesis), *facts),
        warnings=(
            "In sample: the scale c uses the whole sample (future information), as in the "
            "original paper. Only the out-of-sample sections describe what an investor could "
            "have done in real time.",
            "Statistical significance is not economic significance; not rejecting a hypothesis "
            "is not evidence that there is no effect.",
        ),
        sections=tuple(sections),
        footer=(_DISCLAIMER, *_REFERENCES),
    )


def _in_sample_section(frame: pd.DataFrame, significance: float) -> Section:
    rows = tuple(
        (
            str(name),
            f"{row['start']} to {row['end']}",
            str(int(row["n"])),
            _pct(row["alpha_annual"]),
            _num(row["alpha_t"]),
            _num(row["alpha_pvalue"], 4),
            _num(row["alpha_holm"], 4),
            _num(row["alpha_bh"], 4),
            _num(row["beta"]),
            _num(row["appraisal_ratio"]),
            _num(row["r_squared"]),
        )
        for name, row in frame.iterrows()
    )
    table = Table(
        title="Spanning regressions (in sample)",
        columns=(
            "Factor",
            "Sample",
            "N",
            "Alpha p.a.",
            "t (HAC)",
            "p",
            "p Holm",
            "p BH",
            "Beta",
            "Appraisal p.a.",
            "R2",
        ),
        rows=rows,
        align=("left", "left", *("right",) * 9),
        notes=(
            f"Newey-West standard errors; Holm and Benjamini-Hochberg across the "
            f"{len(frame)} factors at {_num(significance, 2)}.",
        ),
    )
    return Section(
        title="In sample: spanning regressions",
        paragraphs=(
            "Managed factor c f_t / RV_{t-1} regressed on the factor; c equalises the full-sample "
            "volatilities, so the Sharpe ratios differ only through the means.",
        ),
        tables=(table,),
        figures=(),
    )


def _out_of_sample_section(
    frame: pd.DataFrame, cap: float, cost: float, significance: float
) -> Section:
    rows = tuple(
        (
            str(row["factor"]),
            f"{row['start']} to {row['end']}",
            str(int(row["n"])),
            _num(row["sharpe_factor"]),
            _num(row["sharpe_managed_net"]),
            _num(row["z_hac"]),
            _num(row["pvalue_hac"], 4),
            _num(row["holm"], 4),
            _num(row["bh"], 4),
            f"[{_num(row['bootstrap_low'], 3)}, {_num(row['bootstrap_high'], 3)}]",
            _num(row["mean_weight"]),
            _num(row["max_weight"]),
            _num(row["annual_turnover"], 1),
        )
        for _, row in frame.iterrows()
    )
    cap_text = "no cap" if math.isinf(cap) else f"cap {_num(cap, 1)}x"
    table = Table(
        title=f"Real-time managed vs unmanaged ({cap_text}, cost {_num(cost * 1e4, 0)} bp)",
        columns=(
            "Factor",
            "Sample",
            "N",
            "Sharpe factor p.a.",
            "Sharpe managed net p.a.",
            "z (HAC)",
            "p",
            "p Holm",
            "p BH",
            "Bootstrap interval (per month)",
            "Mean weight",
            "Max weight",
            "Turnover p.a.",
        ),
        rows=rows,
        align=("left", "left", *("right",) * 11),
        notes=(
            "Ledoit-Wolf HAC test of the per-month Sharpe-ratio difference (managed - factor); "
            f"Holm and Benjamini-Hochberg across factors at {_num(significance, 2)}.",
        ),
    )
    return Section(
        title=f"Out of sample: {cap_text}, cost {_num(cost * 1e4, 0)} bp per unit traded",
        paragraphs=(
            "Weights use only months before each decision (expanding-window scale after the "
            "burn-in); costs are charged on the change in weight.",
        ),
        tables=(table,),
        figures=(),
    )


def _selection_section(deflated: tuple[str, ProbabilisticSharpe, int] | None) -> Section:
    if deflated is None:
        text = "Deflated Sharpe ratio not computed: fewer than two variants were evaluated."
        return Section("Selection across variants", (text,), (), ())
    label, dsr, n_trials = deflated
    return Section(
        title="Selection across variants",
        paragraphs=(
            f"Best out-of-sample variant: {label}. Deflated Sharpe ratio "
            f"{_num(dsr.probability, 3)} with {n_trials} trials (variants in this run times "
            "the configurations recorded in the trial ledger); threshold per-month Sharpe "
            f"{_num(dsr.benchmark, 3)}, observed {_num(dsr.sharpe, 3)}.",
        ),
        tables=(),
        figures=(),
    )


def _num(value: object, decimals: int = 2) -> str:
    number = float(value)  # type: ignore[arg-type]
    if not math.isfinite(number):
        return "n/a"
    return format_number(number, decimals, style=_STYLE)


def _pct(value: object) -> str:
    number = float(value)  # type: ignore[arg-type]
    return format_percent(number, 2, style=_STYLE) if math.isfinite(number) else "n/a"
