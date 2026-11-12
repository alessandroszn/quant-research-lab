r"""Study 3: the factor zoo (Harvey, Liu and Zhu 2016; McLean and Pontiff 2016) on OSAP data.

Design note: ``docs/design/5.3-study-3-factor-zoo.md``.

- **Phases.** For a predictor with original sample years :math:`[S, E]` and publication year
  :math:`P`: months before January of :math:`S` are *pre-sample* (excluded); January of
  :math:`S` to December of :math:`E` are *in-sample*; January of :math:`E+1` to December of
  :math:`P` are *post-sample*; January of :math:`P+1` on are *post-publication*. Only the
  publication year is known, so the publication year itself counts as post-sample.
- **Per-predictor tests.** The mean long-short return of a phase is tested against zero with a
  Newey-West t-statistic (explicit lags, two-sided). Phases with fewer than ``min_months``
  months are not tested and are counted.
- **Decay (McLean-Pontiff).** :math:`r_{it}=\alpha_i+\beta_{ps}\text{PostSample}_{it}
  +\beta_{pp}\text{PostPub}_{it}+\varepsilon_{it}`, predictor fixed effects, errors clustered by
  month; decay is :math:`\beta/\bar r_{in}` with :math:`\bar r_{in}` the pooled in-sample mean.
- **Composites.** Each month, the equal-weighted average of the predictors in a phase; its mean
  is tested with a Newey-West t-statistic.

Returns are monthly long-short returns in decimals, signed as in the original papers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.stats.multiple_testing import Correction, adjust_pvalues
from qrlab.stats.panel import contrast, fixed_effects_ols
from qrlab.stats.regression import CovType, ols

__all__ = [
    "MAX_GAP_SHARE",
    "PHASES",
    "Decay",
    "composites",
    "decay_regression",
    "long_panel",
    "phase_labels",
    "predictor_tests",
    "significance_counts",
]

PHASES = ("in_sample", "post_sample", "post_publication")
MAX_GAP_SHARE = 0.01
"""Largest share of missing months allowed inside a predictor's series (more is suspect)."""


@dataclass(frozen=True)
class Decay:
    """McLean-Pontiff decay regression."""

    beta_post_sample: float
    beta_post_publication: float
    se_post_sample: float
    se_post_publication: float
    p_post_sample: float
    p_post_publication: float
    difference: float  # beta_pp - beta_ps
    p_difference: float
    in_sample_mean: float  # pooled, per month
    decay_post_sample: float  # beta_ps / in_sample_mean
    decay_post_publication: float
    nobs: int
    n_predictors: int
    n_months: int


def phase_labels(
    index: pd.DatetimeIndex, *, start_year: int, end_year: int, publication_year: int
) -> pd.Series:
    """Label each month as pre_sample, in_sample, post_sample or post_publication."""
    for name, value in (
        ("start_year", start_year),
        ("end_year", end_year),
        ("publication_year", publication_year),
    ):
        if type(value) is not int:
            raise ValidationError(f"{name} must be an int, got {value!r}")
    if start_year > end_year:
        raise ValidationError("start_year must not be after end_year")
    years = pd.DatetimeIndex(index).year
    labels = np.select(
        [years < start_year, years <= end_year, years <= publication_year],
        ["pre_sample", "in_sample", "post_sample"],
        default="post_publication",
    )
    return pd.Series(labels, index=index, name="phase")


def long_panel(returns: pd.DataFrame, doc: pd.DataFrame) -> pd.DataFrame:
    """Return one row per predictor and month with its phase (pre-sample months dropped).

    ``doc`` is indexed by acronym with ``Year``, ``SampleStartYear`` and ``SampleEndYear``; every
    predictor in ``doc`` must have a column in ``returns``. Each series runs from its first to
    its last available month; missing months inside it are dropped and, above
    :data:`MAX_GAP_SHARE`, raise.
    """
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise ValidationError("returns need a DatetimeIndex of months")
    missing = sorted(set(doc.index) - set(returns.columns))
    if missing:
        raise ValidationError(f"no returns for predictors {missing[:5]} ({len(missing)} in all)")
    pieces = []
    for name, row in doc.iterrows():
        series = returns[name]
        valid = series.dropna()
        if valid.empty:
            raise ValidationError(f"{name}: no returns")
        span = series.loc[valid.index[0] : valid.index[-1]]
        gaps = int(span.isna().sum())
        if gaps > MAX_GAP_SHARE * len(span):
            raise ValidationError(f"{name}: {gaps} of {len(span)} months missing inside the series")
        phases = phase_labels(
            pd.DatetimeIndex(valid.index),
            start_year=int(row["SampleStartYear"]),
            end_year=int(row["SampleEndYear"]),
            publication_year=int(row["Year"]),
        )
        pieces.append(
            pd.DataFrame(
                {
                    "predictor": str(name),
                    "month": valid.index,
                    "ret": valid.to_numpy(dtype=np.float64),
                    "phase": phases.to_numpy(),
                    "gaps": gaps,
                }
            )
        )
    panel = pd.concat(pieces, ignore_index=True)
    return panel[panel["phase"] != "pre_sample"].reset_index(drop=True)


def predictor_tests(
    panel: pd.DataFrame, *, phase: str, hac_lags: int, min_months: int
) -> pd.DataFrame:
    """Mean, Newey-West t and two-sided p-value of each predictor in ``phase``.

    Predictors with fewer than ``min_months`` months in the phase get NaN statistics.
    """
    if phase not in PHASES:
        raise ValidationError(f"phase must be one of {PHASES}, got {phase!r}")
    if type(min_months) is not int or min_months < 3:
        raise ValidationError("min_months must be an int >= 3")
    rows = {}
    for name, group in panel[panel["phase"] == phase].groupby("predictor", sort=True):
        n = len(group)
        if n < min_months:
            rows[name] = {"mean": np.nan, "t": np.nan, "p": np.nan, "n": n}
            continue
        y = pd.Series(group["ret"].to_numpy(), index=pd.DatetimeIndex(group["month"]))
        fit = ols(
            y,
            pd.DataFrame({"const": 1.0}, index=y.index),
            add_intercept=False,
            cov_type=CovType.HAC,
            hac_lags=hac_lags,
        )
        rows[name] = {
            "mean": float(fit.params["const"]),
            "t": float(fit.tvalues["const"]),
            "p": float(fit.pvalues["const"]),
            "n": n,
        }
    frame = pd.DataFrame.from_dict(rows, orient="index", columns=["mean", "t", "p", "n"])
    frame.index.name = "predictor"
    return frame


def significance_counts(
    tests: pd.DataFrame, *, significance: float, hlz_threshold: float
) -> pd.DataFrame:
    """Count predictors significant under each rule (tested predictors only)."""
    tested = tests.dropna(subset=["p"])
    if tested.empty:
        raise ValidationError("no predictor has enough months to be tested")
    p = tested["p"].astype("float64")
    rules: dict[str, pd.Series] = {
        f"single test, p <= {significance:g}": p <= significance,
        f"t > {hlz_threshold:g} (HLZ)": tested["t"] > hlz_threshold,
    }
    for label, method in (
        ("Holm", Correction.HOLM),
        ("Benjamini-Hochberg", Correction.BENJAMINI_HOCHBERG),
        ("Benjamini-Yekutieli", Correction.BENJAMINI_YEKUTIELI),
    ):
        rules[label] = adjust_pvalues(p, method=method, alpha=significance).rejected
    n = len(tested)
    return pd.DataFrame(
        [
            {
                "rule": rule,
                "significant": int(mask.sum()),
                "positive": int((mask & (tested["t"] > 0)).sum()),
                "tested": n,
                "share": float(mask.sum()) / n,
            }
            for rule, mask in rules.items()
        ]
    ).set_index("rule")


def decay_regression(panel: pd.DataFrame) -> Decay:
    """McLean-Pontiff regression with predictor fixed effects, clustered by month."""
    x = pd.DataFrame(
        {
            "post_sample": (panel["phase"] == "post_sample").astype("float64"),
            "post_publication": (panel["phase"] == "post_publication").astype("float64"),
        }
    )
    result = fixed_effects_ols(
        panel["ret"].astype("float64"), x, entity=panel["predictor"], cluster=panel["month"]
    )
    difference = contrast(result, pd.Series({"post_sample": -1.0, "post_publication": 1.0}))
    in_sample = float(panel.loc[panel["phase"] == "in_sample", "ret"].mean())
    if not (math.isfinite(in_sample) and in_sample != 0.0):
        raise ValidationError("the pooled in-sample mean is zero or undefined")
    b = result.params
    return Decay(
        beta_post_sample=float(b["post_sample"]),
        beta_post_publication=float(b["post_publication"]),
        se_post_sample=float(result.std_errors["post_sample"]),
        se_post_publication=float(result.std_errors["post_publication"]),
        p_post_sample=float(result.pvalues["post_sample"]),
        p_post_publication=float(result.pvalues["post_publication"]),
        difference=difference.estimate,
        p_difference=difference.pvalue,
        in_sample_mean=in_sample,
        decay_post_sample=float(b["post_sample"]) / in_sample,
        decay_post_publication=float(b["post_publication"]) / in_sample,
        nobs=result.nobs,
        n_predictors=result.n_entities,
        n_months=result.n_clusters,
    )


def composites(panel: pd.DataFrame, *, hac_lags: int) -> pd.DataFrame:
    """Equal-weighted composite of the predictors in each phase, month by month, and its test."""
    rows: dict[str, Mapping[str, object]] = {}
    for phase in PHASES:
        part = panel[panel["phase"] == phase]
        if part.empty:
            continue
        by_month = part.groupby("month")["ret"]
        series = by_month.mean()
        series.index = pd.DatetimeIndex(series.index)
        fit = ols(
            series,
            pd.DataFrame({"const": 1.0}, index=series.index),
            add_intercept=False,
            cov_type=CovType.HAC,
            hac_lags=hac_lags,
        )
        rows[phase] = {
            "mean": float(fit.params["const"]),
            "t": float(fit.tvalues["const"]),
            "p": float(fit.pvalues["const"]),
            "months": len(series),
            "average_predictors": float(by_month.size().mean()),
            "start": series.index[0].date().isoformat(),
            "end": series.index[-1].date().isoformat(),
        }
    frame = pd.DataFrame.from_dict(rows, orient="index")
    frame.index.name = "phase"
    return frame
