"""Constraints, 1/N, minimum variance, mean-variance and the frontier.

Hand values (design note 4.2), two assets with sigma 20 % / 10 % and rho 0.3, Sigma =
[[0.04, 0.006], [0.006, 0.01]]: minimum variance (0.105263, 0.894737); mean-variance with
mu = (8 %, 4 %) and lambda 4: (0.368421, 0.631579), return 5.4737 %, variance 0.012211.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.optimization import (
    Constraints,
    efficient_frontier,
    equal_weights,
    mean_variance,
    minimum_variance,
)
from qrlab.risk import CovarianceEstimate

FREE = Constraints(long_only=False, bounds={}, groups={}, turnover=None, current=None)
LONG = Constraints(long_only=True, bounds={}, groups={}, turnover=None, current=None)
MU = pd.Series({"a": 0.08, "b": 0.04})


def _cov(matrix: list[list[float]], names: list[str] | None = None) -> CovarianceEstimate:
    labels = names or [chr(97 + i) for i in range(len(matrix))]
    return CovarianceEstimate(pd.DataFrame(matrix, index=labels, columns=labels), "sample", 60, 0)


SIGMA = _cov([[0.04, 0.006], [0.006, 0.01]])


def test_minimum_variance_hand_example() -> None:
    result = minimum_variance(SIGMA, FREE)
    assert result.weights.to_list() == pytest.approx([0.105263, 0.894737], abs=1e-6)
    inverse = np.linalg.solve(SIGMA.matrix.to_numpy(), np.ones(2))
    assert result.weights.to_numpy() == pytest.approx(inverse / inverse.sum(), abs=1e-9)
    assert result.method == "minimum_variance"
    assert result.inputs["covariance"] == "sample"
    assert result.inputs["constraints"] == "long-short, fully invested"
    assert result.contributions is not None
    assert float(result.contributions.component.sum()) == pytest.approx(result.objective**0.5)


def test_mean_variance_hand_example() -> None:
    result = mean_variance(MU, SIGMA, FREE, risk_aversion=4.0)
    assert result.weights.to_list() == pytest.approx([0.368421, 0.631579], abs=1e-6)
    assert result.inputs["expected_return"] == pytest.approx(0.0547368, abs=1e-7)
    w = result.weights.to_numpy()
    assert float(w @ SIGMA.matrix.to_numpy() @ w) == pytest.approx(0.0122105, abs=1e-7)
    assert result.inputs["risk_aversion"] == 4.0


def test_long_only_binds_when_the_free_solution_shorts() -> None:
    corr = _cov([[0.04, 0.016], [0.016, 0.01]])
    free = minimum_variance(corr, FREE)
    assert free.weights["a"] == pytest.approx(-1 / 3, abs=1e-6)
    bound = minimum_variance(corr, LONG)
    assert bound.weights.to_list() == pytest.approx([0.0, 1.0], abs=1e-9)
    assert "a" in bound.active


def test_bounds_groups_and_turnover() -> None:
    three = _cov([[0.04, 0.0, 0.0], [0.0, 0.02, 0.0], [0.0, 0.0, 0.01]])
    grouped = Constraints(
        long_only=True,
        bounds={"c": (0.0, 0.5)},
        groups={"risky": (("a", "b"), 0.5, 1.0)},
        turnover=None,
        current=None,
    )
    result = minimum_variance(three, grouped)
    w = result.weights
    assert w["c"] == pytest.approx(0.5, abs=1e-8)
    assert w["a"] + w["b"] == pytest.approx(0.5, abs=1e-8)
    assert w["b"] / w["a"] == pytest.approx(2.0, rel=1e-5)  # inverse variance within the group
    current = pd.Series({"a": 0.5, "b": 0.5})
    limited = Constraints(long_only=False, bounds={}, groups={}, turnover=0.10, current=current)
    moved = minimum_variance(SIGMA, limited)
    assert float(np.abs(moved.weights - current).sum()) == pytest.approx(0.10, abs=1e-8)
    assert moved.weights.to_list() == pytest.approx([0.45, 0.55], abs=1e-7)
    assert moved.objective >= minimum_variance(SIGMA, FREE).objective
    assert "turnover <= 10.00%" in moved.inputs["constraints"]  # type: ignore[operator]


def test_frontier_meets_each_target() -> None:
    targets = [0.045, 0.055, 0.07]
    frontier = efficient_frontier(MU, SIGMA, LONG, targets=targets)
    for target, point in zip(targets, frontier, strict=True):
        assert point.weights.to_numpy() @ MU.to_numpy() == pytest.approx(target, abs=1e-8)
        assert point.inputs["target_return"] == target
    variances = [p.objective for p in frontier]
    assert variances[1] < variances[2]
    with pytest.raises(ValidationError, match="infeasible"):
        efficient_frontier(MU, SIGMA, LONG, targets=[0.09])
    with pytest.raises(ValidationError, match="target"):
        efficient_frontier(MU, SIGMA, LONG, targets=[])


def test_equal_weights() -> None:
    result = equal_weights(SIGMA, LONG)
    assert result.weights.to_list() == [0.5, 0.5]
    assert result.iterations == 0
    capped = Constraints(
        long_only=True, bounds={"a": (0.0, 0.4)}, groups={}, turnover=None, current=None
    )
    with pytest.raises(ValidationError, match="1/N"):
        equal_weights(SIGMA, capped)
    grouped = Constraints(
        long_only=True, bounds={}, groups={"g": (("a",), 0.6, 1.0)}, turnover=None, current=None
    )
    with pytest.raises(ValidationError, match="1/N"):
        equal_weights(SIGMA, grouped)
    tight = Constraints(
        long_only=True, bounds={}, groups={}, turnover=0.0, current=pd.Series({"a": 1.0, "b": 0.0})
    )
    with pytest.raises(ValidationError, match="1/N"):
        equal_weights(SIGMA, tight)


def test_zero_volatility_portfolio_has_no_contributions() -> None:
    with_cash = _cov([[0.0, 0.0], [0.0, 0.04]], ["cash", "equity"])
    result = minimum_variance(with_cash, LONG)
    assert result.weights.to_list() == pytest.approx([1.0, 0.0], abs=1e-9)
    assert result.contributions is None


def test_singular_covariance() -> None:
    singular = _cov([[0.01, 0.01], [0.01, 0.01]])
    with pytest.raises(ValidationError, match="not unique"):
        minimum_variance(singular, FREE)
    assert minimum_variance(singular, LONG).weights.sum() == pytest.approx(1.0)


def test_infeasible_and_invalid_constraints() -> None:
    capped = Constraints(
        long_only=True,
        bounds={"a": (0.0, 0.3), "b": (0.0, 0.3)},
        groups={},
        turnover=None,
        current=None,
    )
    with pytest.raises(ValidationError, match="infeasible"):
        minimum_variance(SIGMA, capped)
    with pytest.raises(ValidationError, match="unknown assets"):
        minimum_variance(
            SIGMA,
            Constraints(
                long_only=True, bounds={"z": (0.0, 1.0)}, groups={}, turnover=None, current=None
            ),
        )
    with pytest.raises(ValidationError, match="unknown assets"):
        minimum_variance(
            SIGMA,
            Constraints(
                long_only=True, bounds={}, groups={"g": (("z",), 0, 1)}, turnover=None, current=None
            ),
        )
    with pytest.raises(ValidationError, match="conflict"):
        minimum_variance(
            SIGMA,
            Constraints(
                long_only=True, bounds={"a": (-0.5, -0.1)}, groups={}, turnover=None, current=None
            ),
        )
    with pytest.raises(ValidationError, match="cover exactly"):
        minimum_variance(
            SIGMA,
            Constraints(
                long_only=True, bounds={}, groups={}, turnover=0.1, current=pd.Series({"a": 1.0})
            ),
        )
    for kwargs, match in (
        ({"long_only": 1}, "long_only"),
        ({"bounds": {"a": (0.5, 0.1)}}, "bounds"),
        ({"bounds": {"a": (0.0, float("inf"))}}, "bounds"),
        ({"groups": {"g": ((), 0.0, 1.0)}}, "group"),
        ({"turnover": 0.1}, "go together"),
        ({"turnover": -0.1, "current": pd.Series({"a": 1.0})}, "turnover"),
        ({"turnover": 0.1, "current": pd.Series({"a": 0.5})}, "sum to 1"),
    ):
        fields: dict[str, object] = {
            "long_only": True,
            "bounds": {},
            "groups": {},
            "turnover": None,
            "current": None,
        }
        fields.update(kwargs)
        with pytest.raises(ValidationError, match=match):
            Constraints(**fields)  # type: ignore[arg-type]


def test_input_errors() -> None:
    with pytest.raises(ValidationError, match="risk_aversion"):
        mean_variance(MU, SIGMA, FREE, risk_aversion=0.0)
    with pytest.raises(ValidationError, match="expected returns"):
        mean_variance(pd.Series({"a": 0.1}), SIGMA, FREE, risk_aversion=2.0)
    with pytest.raises(ValidationError, match="finite"):
        mean_variance(pd.Series({"a": np.nan, "b": 0.1}), SIGMA, FREE, risk_aversion=2.0)


def test_describe_lists_every_constraint() -> None:
    c = Constraints(
        long_only=True,
        bounds={"a": (0.0, 0.6)},
        groups={"g": (("a",), 0.0, 1.0)},
        turnover=0.2,
        current=pd.Series({"a": 0.5, "b": 0.5}),
    )
    assert c.describe() == "long-only, fully invested, 1 asset bounds, 1 groups, turnover <= 20.00%"


def test_solver_failures_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from scipy import optimize

    def broken(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            x=np.array([0.7, 0.7]), success=False, message="iteration limit", nit=1
        )

    monkeypatch.setattr(optimize, "minimize", broken)
    with pytest.raises(ValidationError, match="iteration limit"):
        minimum_variance(SIGMA, LONG)


def test_violation_report_names_every_broken_constraint() -> None:
    from qrlab.optimization.constraints import _violations

    w = np.array([0.8, 0.4])
    problems = _violations(
        w,
        np.zeros(2),
        np.array([0.5, 1.0]),
        [(np.array([1.0, 0.0]), 0.0, 0.5)],
        np.array([0.5, 0.5]),
        0.1,
        ((np.array([1.0, 1.0]), 2.0),),
    )
    assert problems[0].startswith("weights sum to 1.2")
    assert problems[1:] == ["bounds", "group bounds", "turnover", "target"]


def test_empty_covariance_raises() -> None:
    empty = CovarianceEstimate(pd.DataFrame(), "sample", 0, 0)
    with pytest.raises(ValidationError, match="no assets"):
        minimum_variance(empty, LONG)


def test_solver_noise_is_snapped_and_tiny_volatility_is_zero() -> None:
    """Regression: CI on some platforms left 2.2e-16 in an asset meant to be 0."""
    from qrlab.optimization.mean_variance import _result

    with_cash = _cov([[0.0, 0.0], [0.0, 0.04]], ["cash", "equity"])
    noisy = _result(with_cash, np.array([1.0, 2.220446e-16]), "x", 0.0, LONG, {}, (), 0)
    assert noisy.contributions is None  # volatility 4.4e-17 is not a risk to allocate
    result = minimum_variance(with_cash, LONG)
    assert result.weights["equity"] == 0.0
