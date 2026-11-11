"""Risk budgeting, maximum diversification, HRP and Black-Litterman (design note 4.2).

Two assets, sigma 20 % / 10 %, rho 0.3: ERC and maximum diversification give (1/3, 2/3);
HRP gives inverse variance (0.2, 0.8). Black-Litterman with market weights (0.6, 0.4),
delta 2.5, tau 0.05: pi = (6.6 %, 1.9 %); the view "asset 1 beats asset 2 by 5 %" with
He-Litterman omega moves the spread from 4.70 % to 4.85 %, exactly halfway.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.optimization import (
    Constraints,
    black_litterman,
    hierarchical_risk_parity,
    maximum_diversification,
    mean_variance,
    risk_budgeting,
)
from qrlab.risk import CovarianceEstimate

FREE = Constraints(long_only=False, bounds={}, groups={}, turnover=None, current=None)
NO_VIEWS = pd.DataFrame(columns=["a", "b"], dtype=float)


def _cov(
    matrix: list[list[float]] | np.ndarray, names: list[str] | None = None
) -> CovarianceEstimate:
    values = np.asarray(matrix, dtype=float)
    labels = names or [chr(97 + i) for i in range(len(values))]
    return CovarianceEstimate(pd.DataFrame(values, index=labels, columns=labels), "sample", 60, 0)


SIGMA = _cov([[0.04, 0.006], [0.006, 0.01]])
EQUAL = pd.Series({"a": 0.5, "b": 0.5})


def test_equal_risk_contribution_hand_example() -> None:
    result = risk_budgeting(SIGMA, EQUAL)
    assert result.weights.to_list() == pytest.approx([1 / 3, 2 / 3], abs=1e-10)
    assert result.method == "equal_risk_contribution"
    assert result.contributions is not None
    assert result.contributions.share.to_list() == pytest.approx([0.5, 0.5], abs=1e-10)


def test_risk_budgets_are_met_with_many_assets(rng: np.random.Generator) -> None:
    raw = rng.normal(size=(200, 5)) @ rng.normal(size=(5, 5)) * 0.01
    cov = _cov(np.cov(raw, rowvar=False))
    budgets = pd.Series([0.4, 0.3, 0.15, 0.1, 0.05], index=list("abcde"))
    result = risk_budgeting(cov, budgets)
    assert result.method == "risk_budgeting"
    assert result.contributions is not None
    assert result.contributions.share.to_numpy() == pytest.approx(budgets.to_numpy(), abs=1e-9)
    assert (result.weights > 0).all()


def test_risk_budgeting_inputs() -> None:
    for budgets in (
        pd.Series({"a": 0.5}),
        pd.Series({"a": 0.7, "b": 0.7}),
        pd.Series({"a": 1.0, "b": 0.0}),
    ):
        with pytest.raises(ValidationError, match="budgets"):
            risk_budgeting(SIGMA, budgets)
    zero = _cov([[0.0, 0.0], [0.0, 0.01]])
    with pytest.raises(ValidationError, match="positive variance"):
        risk_budgeting(zero, EQUAL)


def test_maximum_diversification_hand_example() -> None:
    result = maximum_diversification(SIGMA)
    assert result.weights.to_list() == pytest.approx([1 / 3, 2 / 3], abs=1e-7)
    w = result.weights.to_numpy()
    vol = np.array([0.2, 0.1])
    expected = float(w @ vol / np.sqrt(w @ SIGMA.matrix.to_numpy() @ w))
    assert result.inputs["diversification_ratio"] == pytest.approx(expected)
    with pytest.raises(ValidationError, match="positive volatility"):
        maximum_diversification(_cov([[0.0, 0.0], [0.0, 0.01]]))


def test_hrp_hand_example_and_clusters() -> None:
    result = hierarchical_risk_parity(SIGMA)
    assert result.weights.to_list() == pytest.approx([0.2, 0.8])
    block = np.zeros((4, 4))
    block[:2, :2] = [[0.04, 0.036], [0.036, 0.04]]  # cluster 1: a, b (rho 0.9)
    block[2:, 2:] = [[0.01, 0.009], [0.009, 0.01]]  # cluster 2: c, d (rho 0.9)
    clustered = hierarchical_risk_parity(_cov(block))
    w = clustered.weights
    v1 = 0.25 * (0.04 + 2 * 0.036 + 0.04)  # inverse-variance (equal) weights inside each cluster
    v2 = 0.25 * (0.01 + 2 * 0.009 + 0.01)
    assert w["a"] + w["b"] == pytest.approx(v2 / (v1 + v2))
    assert w["a"] == pytest.approx(w["b"])
    assert w.sum() == pytest.approx(1.0)
    assert hierarchical_risk_parity(_cov([[0.04]])).weights.to_list() == [1.0]
    with pytest.raises(ValidationError, match="positive variance"):
        hierarchical_risk_parity(_cov([[0.0, 0.0], [0.0, 0.01]]))


def test_black_litterman_hand_example() -> None:
    market = pd.Series({"a": 0.6, "b": 0.4})
    views = pd.DataFrame([[1.0, -1.0]], columns=["a", "b"], index=["a over b"])
    bl = black_litterman(
        SIGMA,
        market_weights=market,
        risk_aversion=2.5,
        tau=0.05,
        views=views,
        view_returns=pd.Series([0.05], index=["a over b"]),
        omega=None,
    )
    assert bl.prior.to_list() == pytest.approx([0.066, 0.019])
    spread = float(bl.mean["a"] - bl.mean["b"])
    assert spread == pytest.approx((0.047 + 0.05) / 2)
    assert bl.covariance.estimator == "black_litterman"
    certain = black_litterman(
        SIGMA,
        market_weights=market,
        risk_aversion=2.5,
        tau=0.05,
        views=views,
        view_returns=pd.Series([0.05], index=["a over b"]),
        omega=pd.DataFrame([[1e-12]]),
    )
    assert float(certain.mean["a"] - certain.mean["b"]) == pytest.approx(0.05, abs=1e-8)


def test_black_litterman_without_views_reverses_to_the_market() -> None:
    market = pd.Series({"a": 0.6, "b": 0.4})
    bl = black_litterman(
        SIGMA,
        market_weights=market,
        risk_aversion=2.5,
        tau=0.05,
        views=NO_VIEWS,
        view_returns=pd.Series(dtype=float),
        omega=None,
    )
    assert bl.mean.to_list() == pytest.approx(bl.prior.to_list())
    implied = mean_variance(bl.prior, SIGMA, FREE, risk_aversion=2.5)
    assert implied.weights.to_list() == pytest.approx([0.6, 0.4], abs=1e-7)
    assert bl.covariance.matrix.to_numpy() == pytest.approx(1.05 * SIGMA.matrix.to_numpy())


def test_black_litterman_inputs() -> None:
    market = pd.Series({"a": 0.6, "b": 0.4})
    base = {
        "market_weights": market,
        "risk_aversion": 2.5,
        "tau": 0.05,
        "views": NO_VIEWS,
        "view_returns": pd.Series(dtype=float),
        "omega": None,
    }
    views = pd.DataFrame([[1.0, -1.0]], columns=["a", "b"], index=["v"])
    for changes, match in (
        ({"tau": 0.0}, "tau"),
        ({"risk_aversion": -1.0}, "risk_aversion"),
        ({"market_weights": pd.Series({"a": 1.0})}, "market weights"),
        ({"market_weights": pd.Series({"a": 0.6, "b": 0.6})}, "sum to 1"),
        ({"views": pd.DataFrame([[1.0]], columns=["a"], index=["v"])}, "one column"),
        ({"views": views, "view_returns": pd.Series([0.05], index=["w"])}, "indexed like"),
        (
            {
                "views": views,
                "view_returns": pd.Series([0.05], index=["v"]),
                "omega": pd.DataFrame(np.eye(2)),
            },
            "omega",
        ),
    ):
        with pytest.raises(ValidationError, match=match):
            black_litterman(SIGMA, **{**base, **changes})  # type: ignore[arg-type]


def test_empty_covariance() -> None:
    empty = CovarianceEstimate(pd.DataFrame(), "sample", 0, 0)
    with pytest.raises(ValidationError, match="no assets"):
        hierarchical_risk_parity(empty)
