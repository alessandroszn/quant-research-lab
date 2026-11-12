"""Study 3 (factor zoo): hand-calculated cases first, then properties."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from qrlab.core.errors import ValidationError
from qrlab.studies.factor_zoo import (
    composites,
    decay_regression,
    long_panel,
    phase_labels,
    predictor_tests,
    significance_counts,
)


def _months(start: str, end: str) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq="ME")


# ------------------------------------------------------------------------------------ phases
def test_phases_by_hand() -> None:
    index = pd.DatetimeIndex(
        pd.to_datetime(
            ["1970-12-31", "1971-01-31", "1992-12-31", "1993-01-31", "2001-12-31", "2002-01-31"]
        )
    )
    labels = phase_labels(index, start_year=1971, end_year=1992, publication_year=2001)
    assert labels.tolist() == [
        "pre_sample",
        "in_sample",
        "in_sample",
        "post_sample",
        "post_sample",
        "post_publication",
    ]


def test_publication_before_sample_end_leaves_no_post_sample() -> None:
    index = _months("1999-01-31", "2002-12-31")
    labels = phase_labels(index, start_year=1980, end_year=2000, publication_year=1999)
    assert "post_sample" not in set(labels)
    assert labels.loc["2001-01-31"] == "post_publication"


def test_phase_inputs_are_validated() -> None:
    index = _months("2000-01-31", "2000-03-31")
    with pytest.raises(ValidationError, match="must be an int"):
        phase_labels(index, start_year=1990.0, end_year=1995, publication_year=1996)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="not be after"):
        phase_labels(index, start_year=1996, end_year=1995, publication_year=1997)


# ------------------------------------------------------------------------------ long panel
def _doc(**rows: tuple[int, int, int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            name: {"SampleStartYear": s, "SampleEndYear": e, "Year": p}
            for name, (s, e, p) in rows.items()
        }
    ).T


def test_long_panel_drops_pre_sample_and_counts_gaps() -> None:
    index = _months("1989-01-31", "1994-12-31")
    a = pd.Series(0.01, index=index)
    a.iloc[:6] = np.nan  # starts in July 1989
    returns = pd.DataFrame({"A": a, "B": 0.02, "C": 0.0})
    panel = long_panel(returns, _doc(A=(1990, 1991, 1992), B=(1989, 1993, 1993)))
    assert set(panel["predictor"]) == {"A", "B"}
    a_rows = panel[panel["predictor"] == "A"]
    # 1989 is pre-sample for A; in-sample 1990-1991, post-sample 1992, post-publication 1993-94.
    assert a_rows["phase"].value_counts().to_dict() == {
        "in_sample": 24,
        "post_publication": 24,
        "post_sample": 12,
    }
    b_rows = panel[panel["predictor"] == "B"]
    assert "post_sample" not in set(b_rows["phase"])
    assert (panel["gaps"] == 0).all()


def test_long_panel_gap_rules() -> None:
    index = _months("1990-01-31", "1999-12-31")  # 120 months
    one_gap = pd.Series(0.01, index=index)
    one_gap.iloc[50] = np.nan  # 1 of 120 = 0.8 %: allowed
    panel = long_panel(pd.DataFrame({"A": one_gap}), _doc(A=(1990, 1995, 1996)))
    assert len(panel) == 119
    assert (panel["gaps"] == 1).all()
    two_gaps = one_gap.copy()
    two_gaps.iloc[60] = np.nan  # 2 of 120 = 1.7 %: refused
    with pytest.raises(ValidationError, match="2 of 120 months missing"):
        long_panel(pd.DataFrame({"A": two_gaps}), _doc(A=(1990, 1995, 1996)))
    with pytest.raises(ValidationError, match="no returns for predictors"):
        long_panel(pd.DataFrame({"A": one_gap}), _doc(Z=(1990, 1995, 1996)))
    with pytest.raises(ValidationError, match="A: no returns"):
        long_panel(pd.DataFrame({"A": np.nan}, index=index), _doc(A=(1990, 1995, 1996)))
    with pytest.raises(ValidationError, match="DatetimeIndex"):
        long_panel(pd.DataFrame({"A": [0.01]}), _doc(A=(1990, 1995, 1996)))


# ---------------------------------------------------------------------------- tests and counts
def test_predictor_tests_match_the_classical_t_with_zero_lags(rng: np.random.Generator) -> None:
    index = _months("1990-01-31", "1999-12-31")
    values = rng.normal(0.005, 0.03, len(index))
    panel = pd.DataFrame(
        {"predictor": "A", "month": index, "ret": values, "phase": "in_sample", "gaps": 0}
    )
    tests = predictor_tests(panel, phase="in_sample", hac_lags=0, min_months=12)
    t_classic = values.mean() / (values.std(ddof=1) / math.sqrt(len(values)))
    assert tests.loc["A", "mean"] == pytest.approx(values.mean())
    assert tests.loc["A", "t"] == pytest.approx(t_classic)
    assert tests.loc["A", "p"] == pytest.approx(2 * sps.t.sf(abs(t_classic), len(values) - 1))
    short = predictor_tests(panel, phase="in_sample", hac_lags=0, min_months=200)
    assert np.isnan(short.loc["A", "t"])
    assert short.loc["A", "n"] == 120
    with pytest.raises(ValidationError, match="phase must be one of"):
        predictor_tests(panel, phase="pre_sample", hac_lags=0, min_months=12)
    with pytest.raises(ValidationError, match="min_months"):
        predictor_tests(panel, phase="in_sample", hac_lags=0, min_months=2)


def test_counts_by_hand() -> None:
    t = np.array([1.5, 2.5, 3.5])
    tests = pd.DataFrame(
        {"mean": 0.01, "t": t, "p": 2 * sps.norm.sf(t), "n": 100}, index=["a", "b", "c"]
    )
    tests.loc["d"] = [np.nan, np.nan, np.nan, 5]  # untested (too short)
    counts = significance_counts(tests, significance=0.05, hlz_threshold=3.0)
    # p = 0.134, 0.0124, 0.000465. Single test: 2. t > 3: 1.
    # Holm: 3 x 0.000465, 2 x 0.0124 = 0.0248 -> 2. BH: 0.0014, 0.0186 -> 2.
    # BY (c(3) = 11/6): 0.0026, 0.0341 -> 2.
    assert counts["significant"].tolist() == [2, 1, 2, 2, 2]
    assert (counts["tested"] == 3).all()
    assert counts.loc["t > 3 (HLZ)", "share"] == pytest.approx(1 / 3)
    with pytest.raises(ValidationError, match="no predictor has enough months"):
        significance_counts(tests.iloc[3:], significance=0.05, hlz_threshold=3.0)


# ------------------------------------------------------------------------------ decay and composite
def test_decay_by_hand() -> None:
    months = _months("2000-01-31", "2000-06-30")
    phases = [
        "in_sample",
        "in_sample",
        "post_sample",
        "post_sample",
        "post_publication",
        "post_publication",
    ]
    # Noise with zero mean inside each phase of A, so that the covariance is not degenerate
    # and the estimates stay exact.
    noise = {"A": [0.001, -0.001, 0.003, -0.003, 0.005, -0.005], "B": [0.0] * 6}
    rows = []
    for name, base in (("A", 0.010), ("B", 0.020)):
        for month, phase, e in zip(months, phases, noise[name], strict=True):
            shift = {"in_sample": 0.0, "post_sample": -0.003, "post_publication": -0.006}[phase]
            rows.append((name, month, base + shift + e, phase))
    panel = pd.DataFrame(rows, columns=["predictor", "month", "ret", "phase"])
    decay = decay_regression(panel)
    assert decay.beta_post_sample == pytest.approx(-0.003)
    assert decay.beta_post_publication == pytest.approx(-0.006)
    assert decay.difference == pytest.approx(-0.003)
    # Pooled in-sample mean 1.5 %: decay -20 % and -40 %.
    assert decay.in_sample_mean == pytest.approx(0.015)
    assert decay.decay_post_sample == pytest.approx(-0.2)
    assert decay.decay_post_publication == pytest.approx(-0.4)
    assert (decay.nobs, decay.n_predictors, decay.n_months) == (12, 2, 6)
    zero = panel.assign(ret=np.where(panel["phase"] == "in_sample", 0.0, panel["ret"]))
    with pytest.raises(ValidationError, match="pooled in-sample mean"):
        decay_regression(zero)


def test_composite_by_hand(rng: np.random.Generator) -> None:
    months = _months("2000-01-31", "2004-12-31")
    rows = [("A", m, 0.01 + rng.normal(0, 0.01), "post_publication") for m in months]
    rows += [("B", m, 0.03 + rng.normal(0, 0.01), "post_publication") for m in months]
    rows += [("C", m, 0.02, "in_sample") for m in months[:30]] + [
        ("C", m, 0.02 + 0.001 * (i % 3), "in_sample") for i, m in enumerate(months[30:])
    ]
    panel = pd.DataFrame(rows, columns=["predictor", "month", "ret", "phase"])
    table = composites(panel, hac_lags=3)
    assert list(table.index) == ["in_sample", "post_publication"]
    first = panel[(panel["phase"] == "post_publication") & (panel["month"] == months[0])]
    expected = float(first["ret"].mean())
    composite = panel[panel["phase"] == "post_publication"].groupby("month")["ret"].mean()
    assert composite.iloc[0] == pytest.approx(expected)
    assert table.loc["post_publication", "mean"] == pytest.approx(float(composite.mean()))
    assert table.loc["post_publication", "average_predictors"] == 2.0
    assert table.loc["post_publication", "months"] == 60


def test_report_needs_counts_and_composites() -> None:
    from qrlab.studies.factor_zoo import Decay
    from qrlab.studies.factor_zoo_report import build_factor_zoo_report

    decay = Decay(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1, 1, 1)
    with pytest.raises(ValidationError, match="in-sample counts and the composites"):
        build_factor_zoo_report(
            title="T",
            hypothesis="H",
            facts=(),
            counts_in_sample=pd.DataFrame(),
            counts_post_publication=pd.DataFrame(),
            decay=decay,
            composites=pd.DataFrame(),
        )
