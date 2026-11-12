"""Multiple-testing corrections (hand values from design note 5.1, cross-checked with statsmodels).

p = (0.01, 0.04, 0.03, 0.005): Holm (0.03, 0.06, 0.06, 0.02), rejecting the first and fourth
at 5 %; Benjamini-Hochberg (0.02, 0.04, 0.04, 0.02), rejecting all four; Benjamini-Yekutieli is
BH times c(4) = 2.0833, capped at 1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

from qrlab.core.errors import ValidationError
from qrlab.stats.multiple_testing import Correction, adjust_pvalues

P = pd.Series([0.01, 0.04, 0.03, 0.005], index=["a", "b", "c", "d"])


def test_holm_hand_example() -> None:
    result = adjust_pvalues(P, method=Correction.HOLM, alpha=0.05)
    assert result.adjusted.to_list() == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert result.rejected.to_list() == [True, False, False, True]
    assert (result.m, result.alpha, result.method) == (4, 0.05, Correction.HOLM)


def test_benjamini_hochberg_hand_example() -> None:
    result = adjust_pvalues(P, method=Correction.BENJAMINI_HOCHBERG, alpha=0.05)
    assert result.adjusted.to_list() == pytest.approx([0.02, 0.04, 0.04, 0.02])
    assert result.rejected.all()


def test_benjamini_yekutieli_hand_example() -> None:
    result = adjust_pvalues(P, method=Correction.BENJAMINI_YEKUTIELI, alpha=0.05)
    c4 = 1 + 1 / 2 + 1 / 3 + 1 / 4
    assert result.adjusted.to_list() == pytest.approx(
        [min(1.0, c4 * v) for v in (0.02, 0.04, 0.04, 0.02)]
    )


@pytest.mark.parametrize(
    ("method", "name"),
    [
        (Correction.HOLM, "holm"),
        (Correction.BENJAMINI_HOCHBERG, "fdr_bh"),
        (Correction.BENJAMINI_YEKUTIELI, "fdr_by"),
    ],
)
def test_matches_statsmodels(method: Correction, name: str, rng: np.random.Generator) -> None:
    p = pd.Series(rng.uniform(0, 0.2, 40) ** 2)
    ours = adjust_pvalues(p, method=method, alpha=0.1)
    reject, adjusted, _, _ = multipletests(p.to_numpy(), alpha=0.1, method=name)
    np.testing.assert_allclose(ours.adjusted.to_numpy(), adjusted, rtol=1e-12)
    assert ours.rejected.to_list() == reject.tolist()


def test_single_hypothesis_and_ties() -> None:
    one = adjust_pvalues(pd.Series({"x": 0.03}), method=Correction.HOLM, alpha=0.05)
    assert one.adjusted.to_list() == [0.03]
    ties = adjust_pvalues(pd.Series([0.02, 0.02]), method=Correction.BENJAMINI_HOCHBERG, alpha=0.05)
    assert ties.adjusted.to_list() == pytest.approx([0.02, 0.02])


def test_input_errors() -> None:
    for bad in (
        pd.Series([0.1, 1.2]),
        pd.Series([0.1, np.nan]),
        pd.Series([-0.1]),
        pd.Series(dtype=float),
    ):
        with pytest.raises(ValidationError):
            adjust_pvalues(bad, method=Correction.HOLM, alpha=0.05)
    with pytest.raises(ValidationError, match="unique"):
        adjust_pvalues(pd.Series([0.1, 0.2], index=["a", "a"]), method=Correction.HOLM, alpha=0.05)
    with pytest.raises(ValidationError, match="alpha"):
        adjust_pvalues(P, method=Correction.HOLM, alpha=1.0)
    with pytest.raises(ValidationError, match="Correction"):
        adjust_pvalues(P, method="holm", alpha=0.05)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="Series"):
        adjust_pvalues([0.1], method=Correction.HOLM, alpha=0.05)  # type: ignore[arg-type]
