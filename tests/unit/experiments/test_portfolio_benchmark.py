"""The portfolio against a benchmark (design note 11.2), with hand values.

Three monthly periods: portfolio r = (2, -1, 3) %, benchmark b = (1, 0, 2) %, active
a = (1, -1, 1) %:

- mean a = 1/3 %, s_a = sqrt(4/3) % = 1.154701 %;
- tracking error = sqrt(4/3) x sqrt(12) % = 4.00 %;
- information ratio = (12 x 1/3 %) / 4 % = 1.00;
- cumulative: 1.02 x 0.99 x 1.03 - 1 = 4.0094 % against 1.01 x 1.00 x 1.02 - 1 = 3.02 %;
- beta on plain returns: S_xy / S_xx = 4 / 2 = 2.0, alpha = 4/3 - 2 x 1 = -2/3 % a month,
  -8 % a year;
- with a constant risk-free rate rf, beta is unchanged and alpha becomes alpha + rf (beta - 1):
  rf = 0.1 % a month gives -2/3 % + 0.1 % a month, -6.8 % a year.

Currency: a USD benchmark at 100 -> 110 while EUR/USD goes 1.25 -> 1.10 is 80 -> 100 in EUR,
a +25 % return.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.data import parse_ecb_fx
from qrlab.data.provenance import Dataset, Provenance
from qrlab.experiments.kinds._portfolio_benchmark import BenchmarkSpec, compare, parse_benchmark

EUR, USD = Currency("EUR"), Currency("USD")
D0, D1, D2, D3 = date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 31), date(2026, 4, 30)
DATES = [D0, D1, D2, D3]
SPEC = BenchmarkSpec("Example index, net total return")


def _series(values: list[float], days: list[date], name: str = "x") -> pd.Series:
    return pd.Series(values, index=pd.DatetimeIndex([pd.Timestamp(d) for d in days]), name=name)


def _twr(first: float | None = 0.001) -> pd.Series:
    """TWR with a start-of-day return on the first date (left out of the comparison)."""
    values = [0.02, -0.01, 0.03]
    days = [D1, D2, D3]
    if first is not None:
        values, days = [first, *values], [D0, *days]
    return _series(values, days, "TWR")


LEVELS = _series([100.0, 101.0, 101.0, 103.02], DATES)


def _compare(**changes: object) -> object:
    arguments: dict[str, object] = {
        "level": LEVELS,
        "currency": EUR,
        "base": EUR,
        "fx": None,
        "fx_max_age_days": None,
        "max_price_age_days": 0,
        "dates": DATES,
        "twr_returns": _twr(),
        "risk_free": None,
        "monthly": True,
    }
    return compare(SPEC, **(arguments | changes))  # type: ignore[arg-type]


def _fx(lines: str) -> Dataset:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("eurofxref-hist.csv", lines)
    data = content.getvalue()
    provenance = Provenance(
        source="ecb", dataset="eurofxref-hist", url="file:fx.zip",
        retrieved_at=datetime(2026, 5, 1, tzinfo=UTC), sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data), terms="synthetic",
    )  # fmt: skip
    return parse_ecb_fx(data, provenance)


def test_three_months_by_hand() -> None:
    out = _compare()
    s = out.summary  # type: ignore[attr-defined]
    assert (s.window_start, s.window_end, s.n_periods) == (D1, D3, 3)  # the first date is out
    assert s.portfolio_total == pytest.approx(1.02 * 0.99 * 1.03 - 1.0, abs=1e-12)
    assert s.benchmark_total == pytest.approx(0.0302, abs=1e-12)
    assert s.tracking_error == pytest.approx(0.04, abs=1e-12)
    assert s.information_ratio == pytest.approx(1.0, abs=1e-12)
    assert s.capm.beta == pytest.approx(2.0, abs=1e-12)
    assert s.capm.alpha_annualised == pytest.approx(-0.08, abs=1e-12)
    assert s.capm.n == 3
    assert not s.on_excess
    assert s.reasons == {}
    assert s.carried == ()
    table = out.table  # type: ignore[attr-defined]
    assert table["active"].tolist() == pytest.approx([0.01, -0.01, 0.01], abs=1e-12)
    scalars = out.scalars  # type: ignore[attr-defined]
    assert scalars["active_total"] == pytest.approx(1.02 * 0.99 * 1.03 - 1.0302, abs=1e-12)
    assert set(scalars) == {
        "benchmark_total", "active_total", "tracking_error", "information_ratio", "beta",
        "beta_se", "alpha_annual", "alpha_annual_se", "r_squared",
    }  # fmt: skip
    assert out.portfolio_returns.index.equals(out.benchmark_returns.index)  # type: ignore[attr-defined]


def test_end_of_day_timing_has_no_first_return() -> None:
    out = _compare(twr_returns=_twr(first=None))
    assert out.summary.n_periods == 3  # type: ignore[attr-defined]
    assert out.summary.tracking_error == pytest.approx(0.04, abs=1e-12)  # type: ignore[attr-defined]


def test_a_constant_risk_free_rate_moves_alpha_only() -> None:
    rf = _series([0.001, 0.001, 0.001], [D1, D2, D3])
    out = _compare(risk_free=rf)
    s = out.summary  # type: ignore[attr-defined]
    assert s.on_excess
    assert s.capm.beta == pytest.approx(2.0, abs=1e-12)
    assert s.capm.alpha_annualised == pytest.approx(12 * (-0.02 / 3 + 0.001), abs=1e-12)
    table = out.table  # type: ignore[attr-defined]
    assert table["excess_portfolio"].tolist() == pytest.approx([0.019, -0.011, 0.029])
    assert s.tracking_error == pytest.approx(0.04, abs=1e-12)  # unchanged by the risk-free
    with pytest.raises(ValidationError, match="does not cover"):
        _compare(risk_free=rf.iloc[:2])


def test_a_foreign_benchmark_is_valued_in_the_base_currency() -> None:
    fx = _fx("Date,USD,\n2026-02-27,1.10,\n2026-01-30,1.25,\n")
    out = _compare(
        level=_series([100.0, 110.0], [D0, D1]), currency=USD, fx=fx, fx_max_age_days=0,
        dates=[D0, D1], twr_returns=_series([0.02], [D1]), monthly=False,
    )  # fmt: skip
    assert out.benchmark_returns.tolist() == pytest.approx([0.25], abs=1e-12)  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="needs an fx input"):
        _compare(currency=USD)


def test_carried_values_are_listed_and_old_ones_refused() -> None:
    gap = _series([100.0, 101.0, 103.02], [D0, D1, D3])  # no level on D2 (31 March)
    out = _compare(level=gap, max_price_age_days=40)
    assert out.summary.carried == (("level", D2, D1),)  # type: ignore[attr-defined]
    assert out.benchmark_returns.tolist() == pytest.approx([0.01, 0.0, 0.02])  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="older than 0 days"):
        _compare(level=gap)
    with pytest.raises(ValidationError, match="no benchmark level on or before"):
        _compare(level=LEVELS.iloc[1:])
    fx = _fx("Date,USD,\n2026-04-30,1.0,\n2026-02-27,1.0,\n2026-01-30,1.0,\n")
    out = _compare(currency=USD, fx=fx, fx_max_age_days=40)
    assert ("USD rate", D2, D1) in out.summary.carried  # type: ignore[attr-defined]


def test_measures_that_do_not_exist_say_why() -> None:
    daily = _compare(monthly=False).summary  # type: ignore[attr-defined]
    assert daily.tracking_error is None
    assert daily.capm is None
    assert "monthly" in daily.reasons["capm"]
    assert daily.portfolio_total is not None  # the cumulative returns need no frequency
    two = _compare(dates=DATES[:3], twr_returns=_twr().iloc[:3]).summary  # type: ignore[attr-defined]
    assert two.tracking_error is not None
    assert "at least 3" in two.reasons["capm"]
    none = _compare(dates=[D0], twr_returns=_twr().iloc[:1]).summary  # type: ignore[attr-defined]
    assert none.n_periods == 0
    assert none.window_start is None
    assert none.portfolio_total is None


def test_cross_check_against_numpy(rng: np.random.Generator) -> None:
    days = [d.date() for d in pd.date_range("2020-01-31", periods=37, freq="ME")]
    levels = _series(list(100.0 * np.cumprod(1.0 + rng.normal(0.005, 0.03, 37))), days)
    r = rng.normal(0.006, 0.035, 36)
    out = _compare(level=levels, dates=days, twr_returns=_series(list(r), days[1:])).summary  # type: ignore[attr-defined]
    b = levels.to_numpy()[1:] / levels.to_numpy()[:-1] - 1.0
    assert out.tracking_error == pytest.approx(np.std(r - b, ddof=1) * np.sqrt(12), rel=1e-12)
    slope, intercept = np.polyfit(b, r, 1)
    assert out.capm.beta == pytest.approx(slope, rel=1e-10)
    assert out.capm.alpha_annualised == pytest.approx(12 * intercept, rel=1e-9)


def test_parse_benchmark() -> None:
    assert parse_benchmark({}) is None
    assert parse_benchmark({"benchmark": {"name": "Index"}}) == BenchmarkSpec("Index")
    with pytest.raises(ValidationError, match="must be a table"):
        parse_benchmark({"benchmark": "Index"})
    with pytest.raises(ValidationError, match="name"):
        parse_benchmark({"benchmark": {}})
