"""Fixed-effects OLS with clustered errors: hand case, then statsmodels with dummies."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from qrlab.core.errors import ValidationError
from qrlab.stats.panel import contrast, fixed_effects_ols


def _panel(rng: np.random.Generator, entities: int = 6, periods: int = 40) -> pd.DataFrame:
    rows = []
    for e in range(entities):
        alpha = rng.normal(0.0, 1.0)
        for t in range(periods):
            post = float(t >= 15 + e)
            late = float(t >= 28 + e // 2)
            shock = rng.normal(0.0, 0.5)
            rows.append((f"e{e}", t, post, late, alpha - 0.3 * post - 0.2 * late + shock))
    return pd.DataFrame(rows, columns=["entity", "month", "post", "late", "y"])


def test_hand_case_shifts_are_recovered_exactly() -> None:
    # A: 1.0 in, 0.7 post-sample, 0.4 post-publication; B: 2.0, 1.7, 1.4 (two months each).
    y = pd.Series([1.0, 1.0, 0.7, 0.7, 0.4, 0.4, 2.0, 2.0, 1.7, 1.7, 1.4, 1.4])
    post_sample = pd.Series([0, 0, 1, 1, 0, 0] * 2, dtype=float)
    post_pub = pd.Series([0, 0, 0, 0, 1, 1] * 2, dtype=float)
    x = pd.DataFrame({"post_sample": post_sample, "post_pub": post_pub})
    entity = pd.Series(["A"] * 6 + ["B"] * 6)
    cluster = pd.Series(list(range(6)) * 2)
    result = fixed_effects_ols(y, x, entity=entity, cluster=cluster)
    assert result.params.to_numpy() == pytest.approx([-0.3, -0.6])
    assert result.nobs == 12
    assert result.n_entities == 2
    assert result.n_clusters == 6


def test_matches_statsmodels_with_dummies(rng: np.random.Generator) -> None:
    panel = _panel(rng)
    x = panel[["post", "late"]]
    result = fixed_effects_ols(panel["y"], x, entity=panel["entity"], cluster=panel["month"])
    dummies = pd.get_dummies(panel["entity"], dtype=float)
    design = pd.concat([x, dummies], axis=1)
    fit = sm.OLS(panel["y"], design).fit(
        cov_type="cluster", cov_kwds={"groups": panel["month"]}, use_t=True
    )
    assert result.params.to_numpy() == pytest.approx(fit.params[["post", "late"]].to_numpy())
    assert result.std_errors.to_numpy() == pytest.approx(fit.bse[["post", "late"]].to_numpy())
    assert result.pvalues.to_numpy() == pytest.approx(fit.pvalues[["post", "late"]].to_numpy())
    test = contrast(result, pd.Series({"post": -1.0, "late": 1.0}))
    reference = fit.t_test(np.r_[-1.0, 1.0, np.zeros(dummies.shape[1])])
    assert test.estimate == pytest.approx(float(reference.effect[0]))
    assert test.std_error == pytest.approx(float(reference.sd[0, 0]))
    assert test.pvalue == pytest.approx(float(reference.pvalue))


def test_inputs_are_validated(rng: np.random.Generator) -> None:
    panel = _panel(rng, entities=3, periods=10)
    y, x, ent, cl = panel["y"], panel[["post"]], panel["entity"], panel["month"]
    with pytest.raises(ValidationError, match="must be a pandas Series"):
        fixed_effects_ols(y.to_numpy(), x, entity=ent, cluster=cl)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="at least one regressor"):
        fixed_effects_ols(y, x.iloc[:, :0], entity=ent, cluster=cl)
    with pytest.raises(ValidationError, match="same index"):
        fixed_effects_ols(y, x, entity=ent.iloc[1:], cluster=cl)
    with pytest.raises(ValidationError, match="same index"):
        fixed_effects_ols(y, x, entity=ent, cluster=cl.iloc[1:])
    with pytest.raises(ValidationError, match="must not be missing"):
        fixed_effects_ols(y, x, entity=ent.where(ent != "e0"), cluster=cl)
    with pytest.raises(ValidationError, match="finite"):
        fixed_effects_ols(y.where(y > 0), x, entity=ent, cluster=cl)
    with pytest.raises(ValidationError, match="two clusters"):
        fixed_effects_ols(y, x, entity=ent, cluster=pd.Series(0, index=y.index))
    with pytest.raises(ValidationError, match="observations for"):
        # 2 rows, 1 regressor, 1 entity: no degrees of freedom left.
        fixed_effects_ols(y.iloc[:2], x.iloc[:2], entity=ent.iloc[:2], cluster=cl.iloc[:2])
    absorbed = pd.DataFrame({"by_entity": pd.factorize(ent)[0].astype(float)}, index=y.index)
    with pytest.raises(ValidationError, match="absorbed"):
        fixed_effects_ols(y, absorbed, entity=ent, cluster=cl)


def test_contrast_validation(rng: np.random.Generator) -> None:
    panel = _panel(rng)
    result = fixed_effects_ols(
        panel["y"], panel[["post", "late"]], entity=panel["entity"], cluster=panel["month"]
    )
    with pytest.raises(ValidationError, match="name every coefficient"):
        contrast(result, pd.Series({"post": 1.0}))
    with pytest.raises(ValidationError, match="zero variance"):
        contrast(result, pd.Series({"post": 0.0, "late": 0.0}))
