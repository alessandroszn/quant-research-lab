"""Factor and currency attribution (hand values from design note 4.4).

- a_t = 0.001 + 0.5 f_t exactly: beta 0.5, alpha 0.001, residual 0;
- one USD asset at weight 1, local +10 %, USD -5 %: base +4.5 % = 10 % - 5 % - 0.5 %.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.attribution import currency_attribution, factor_attribution
from qrlab.core.errors import ValidationError
from qrlab.stats.regression import CovType, ols


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2015-01-31", periods=n, freq="ME")


def test_exact_factor_model_hand_example(rng: np.random.Generator) -> None:
    f = pd.DataFrame({"mkt": rng.normal(0.0, 0.04, 60)}, index=_index(60))
    active = 0.001 + 0.5 * f["mkt"]
    result = factor_attribution(active, f, cov_type=CovType.NONROBUST, hac_lags=None)
    assert result.betas["mkt"] == pytest.approx(0.5)
    assert result.alpha == pytest.approx(0.001)
    assert result.residual_total == pytest.approx(0.0, abs=1e-14)
    assert result.contributions["mkt"] == pytest.approx(0.5 * float(f["mkt"].sum()))
    assert result.r_squared == pytest.approx(1.0)


def test_noisy_factor_model_matches_ols_and_adds_up(rng: np.random.Generator) -> None:
    f = pd.DataFrame(
        rng.normal(0.0, 0.03, size=(120, 2)), index=_index(120), columns=["mkt", "val"]
    )
    active = pd.Series(
        0.0005 + 0.3 * f["mkt"] - 0.2 * f["val"] + rng.normal(0.0, 0.01, 120), index=f.index
    )
    result = factor_attribution(active, f, cov_type=CovType.HAC, hac_lags=3)
    reference = ols(active, f, add_intercept=True, cov_type=CovType.HAC, hac_lags=3)
    assert result.betas.to_list() == pytest.approx(reference.params.drop("const").to_list())
    assert result.alpha_se == pytest.approx(float(reference.std_errors["const"]))
    explained = result.alpha_total + float(result.contributions.sum())
    assert explained + result.residual_total == pytest.approx(result.active_total, abs=1e-15)
    assert result.residual_total == pytest.approx(0.0, abs=1e-12)
    assert result.alpha_significant is (abs(result.alpha_t) >= 2.0)
    assert (result.n_obs, result.cov_type) == (120, "hac")


def test_currency_hand_example() -> None:
    one = pd.Series({"US": 1.0})
    result = currency_attribution(
        one, one, pd.Series({"US": 0.10}), pd.Series({"US": 0.10}), pd.Series({"US": -0.05})
    )
    split = result.portfolio
    assert [split.local, split.currency, split.cross] == pytest.approx([0.10, -0.05, -0.005])
    assert split.total == pytest.approx(1.10 * 0.95 - 1)
    assert result.active.total == 0.0


def test_currency_active_parts_add_up() -> None:
    wp = pd.Series({"EU": 0.4, "US": 0.6})
    wb = pd.Series({"EU": 0.6, "US": 0.4})
    lp = pd.Series({"EU": 0.05, "US": 0.12})
    lb = pd.Series({"EU": 0.04, "US": 0.10})
    fx = pd.Series({"EU": 0.0, "US": -0.08})
    result = currency_attribution(wp, wb, lp, lb, fx)
    base_p = float((wp * ((1 + lp) * (1 + fx) - 1)).sum())
    base_b = float((wb * ((1 + lb) * (1 + fx) - 1)).sum())
    assert result.portfolio.total == pytest.approx(base_p)
    assert result.active.total == pytest.approx(base_p - base_b)
    assert result.active.currency == pytest.approx(0.2 * -0.08)


def test_currency_input_errors() -> None:
    one = pd.Series({"US": 1.0})
    with pytest.raises(ValidationError, match="cover exactly"):
        currency_attribution(one, pd.Series({"EU": 1.0}), one * 0.1, one * 0.1, one * 0.0)
    with pytest.raises(ValidationError, match="sum to 1"):
        currency_attribution(one * 0.5, one, one * 0.1, one * 0.1, one * 0.0)
    with pytest.raises(ValidationError, match="finite"):
        currency_attribution(one, one, one * np.nan, one * 0.1, one * 0.0)
