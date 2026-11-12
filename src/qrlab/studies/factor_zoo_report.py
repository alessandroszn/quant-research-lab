"""HTML report of study 3 (the factor zoo): original-sample and later results kept apart."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.reporting.formatting import Language, format_number, format_percent, style_for
from qrlab.reporting.html import Report, Section
from qrlab.reporting.tables import Table
from qrlab.studies.factor_zoo import Decay

__all__ = ["build_factor_zoo_report"]

_STYLE = style_for(Language.EN)
_REFERENCES = (
    "Chen, A. Y. and Zimmermann, T. (2022), Open source cross-sectional asset pricing, Critical "
    "Finance Review 11(2). Data: Open Source Asset Pricing, CC BY 4.0.",
    "Harvey, C. R., Liu, Y. and Zhu, H. (2016), ... and the cross-section of expected returns, "
    "Review of Financial Studies 29(1).",
    "McLean, R. D. and Pontiff, J. (2016), Does academic research destroy stock return "
    "predictability?, Journal of Finance 71(1).",
)


def build_factor_zoo_report(
    *,
    title: str,
    hypothesis: str,
    facts: Sequence[tuple[str, str]],
    counts_in_sample: pd.DataFrame,
    counts_post_publication: pd.DataFrame,
    decay: Decay,
    composites: pd.DataFrame,
) -> Report:
    """Assemble the report from the tables of :mod:`qrlab.studies.factor_zoo`."""
    if counts_in_sample.empty or composites.empty:
        raise ValidationError("the report needs the in-sample counts and the composites")
    return Report(
        title=title,
        language=Language.EN,
        facts=(("Hypothesis", hypothesis), *facts),
        warnings=(
            "In-sample tests use each original paper's sample and sign: they are biased upward "
            "by construction (the predictor was published because it worked there).",
            "Gross long-short returns of paper portfolios: no trading costs.",
        ),
        sections=(
            _counts_section(
                "Original samples: how many predictors are significant (H1)",
                counts_in_sample,
                "Each predictor's mean long-short return over its original sample, Newey-West "
                "t-statistic, two-sided p-value; corrections across the predictors tested.",
            ),
            _decay_section(decay),
            _composites_section(composites),
            _counts_section(
                "After publication: the same counts (context, not a hypothesis)",
                counts_post_publication,
                "Same tests on each predictor's post-publication months.",
            ),
        ),
        footer=("Research analytics, not investment advice.", *_REFERENCES),
    )


def _counts_section(title: str, counts: pd.DataFrame, note: str) -> Section:
    rows = tuple(
        (
            str(rule),
            str(int(row["significant"])),
            str(int(row["positive"])),
            str(int(row["tested"])),
            _pct(row["share"]),
        )
        for rule, row in counts.iterrows()
    )
    table = Table(
        title=title,
        columns=("Rule", "Significant", "Of which positive", "Tested", "Share"),
        rows=rows,
        align=("left", "right", "right", "right", "right"),
        notes=(note,),
    )
    return Section(title=title, paragraphs=(), tables=(table,), figures=())


def _decay_section(d: Decay) -> Section:
    rows = (
        (
            "Post-sample",
            _pct(d.beta_post_sample, 3),
            _pct(d.se_post_sample, 3),
            _num(d.p_post_sample, 4),
            _pct(d.decay_post_sample, 1),
        ),
        (
            "Post-publication",
            _pct(d.beta_post_publication, 3),
            _pct(d.se_post_publication, 3),
            _num(d.p_post_publication, 4),
            _pct(d.decay_post_publication, 1),
        ),
        (
            "Post-publication minus post-sample",
            _pct(d.difference, 3),
            "",
            _num(d.p_difference, 4),
            "",
        ),
    )
    table = Table(
        title="McLean-Pontiff decay (H2)",
        columns=("Coefficient", "Estimate / month", "Std. error", "p", "Decay of in-sample mean"),
        rows=rows,
        align=("left", "right", "right", "right", "right"),
        notes=(
            f"Predictor fixed effects, errors clustered by month. {d.nobs} predictor-months, "
            f"{d.n_predictors} predictors, {d.n_months} months; pooled in-sample mean "
            f"{_pct(d.in_sample_mean, 3)} per month.",
        ),
    )
    return Section(
        title="Decay after the sample and after publication (H2)",
        paragraphs=(),
        tables=(table,),
        figures=(),
    )


def _composites_section(frame: pd.DataFrame) -> Section:
    rows = tuple(
        (
            str(phase).replace("_", " "),
            f"{row['start']} to {row['end']}",
            str(int(row["months"])),
            _num(row["average_predictors"], 1),
            _pct(row["mean"], 3),
            _num(row["t"]),
            _num(row["p"], 4),
        )
        for phase, row in frame.iterrows()
    )
    table = Table(
        title="Equal-weighted composite by phase (H3)",
        columns=("Phase", "Months", "N", "Predictors / month", "Mean / month", "t (HAC)", "p"),
        rows=rows,
        align=("left", "left", "right", "right", "right", "right", "right"),
        notes=("Each month, the average long-short return of the predictors in that phase.",),
    )
    return Section(title="Composites (H3)", paragraphs=(), tables=(table,), figures=())


def _num(value: object, decimals: int = 2) -> str:
    number = float(value)  # type: ignore[arg-type]
    return format_number(number, decimals, style=_STYLE) if math.isfinite(number) else "n/a"


def _pct(value: object, decimals: int = 2) -> str:
    number = float(value)  # type: ignore[arg-type]
    return format_percent(number, decimals, style=_STYLE) if math.isfinite(number) else "n/a"
