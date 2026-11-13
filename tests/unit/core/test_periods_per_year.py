"""``periods_per_year`` must not contradict the dates (design note 7.1), hand-checked cases."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from qrlab.core import ValidationError, require_periods_per_year


def _dates(freq: str, n: int = 24, start: str = "2020-01-31") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq=freq)


@pytest.mark.parametrize(
    ("freq", "accepted", "refused"),
    [
        ("ME", [12, 12.0], [252, 4, 11, 13]),
        ("B", [252, 250, 262, 365, 366], [12, 249, 367]),
        ("W-FRI", [52, 52.18, 50, 53], [12, 365]),
        ("QE", [4], [12, 1]),
        ("YE", [1], [12, 4]),
    ],
)
def test_accepted_and_refused_values(
    freq: str, accepted: list[float], refused: list[float]
) -> None:
    index = _dates(freq)
    for value in accepted:
        assert require_periods_per_year(value, index) == float(value)
    for value in refused:
        with pytest.raises(ValidationError, match="but the dates are"):
            require_periods_per_year(value, index)


def test_the_message_says_what_to_use() -> None:
    with pytest.raises(ValidationError) as info:
        require_periods_per_year(252, _dates("ME"))
    message = str(info.value)
    assert "periods_per_year is 252" in message
    assert "monthly" in message
    assert "use 12" in message
    with pytest.raises(ValidationError, match=r"daily .* use 252"):
        require_periods_per_year(12, _dates("B"))


def test_no_check_when_the_frequency_cannot_be_known() -> None:
    irregular = pd.DatetimeIndex(["2020-01-01", "2020-01-11", "2020-01-21", "2020-01-31"])
    assert require_periods_per_year(252, irregular) == 252.0  # median gap of 10 days
    assert require_periods_per_year(252, pd.RangeIndex(10)) == 252.0
    assert require_periods_per_year(252, pd.DatetimeIndex(["2020-01-31"])) == 252.0
    assert require_periods_per_year(12, None) == 12.0


def test_unsorted_dates_are_judged_by_their_gaps() -> None:
    monthly = _dates("ME")[::-1]
    with pytest.raises(ValidationError, match="monthly"):
        require_periods_per_year(252, monthly)


@pytest.mark.parametrize("bad", [0, -12, math.nan, math.inf, True, "12", None])
def test_bad_values_raise(bad: object) -> None:
    with pytest.raises(ValidationError, match="periods_per_year must be"):
        require_periods_per_year(bad, _dates("ME"))  # type: ignore[arg-type]


# ------------------------------------------------------------------------ where it is applied
def test_metrics_refuse_a_contradicting_value() -> None:
    from qrlab.metrics import SharpeSE, annualised_volatility, sharpe_ratio, tracking_error

    r = pd.Series([0.01, -0.02, 0.03, 0.00], index=_dates("ME", n=4))
    # Hand value with 12: sample std of (0.01, -0.02, 0.03, 0.00) is 0.0208167; times sqrt(12).
    assert annualised_volatility(r, periods_per_year=12) == pytest.approx(0.0721110, abs=1e-6)
    for call in (
        lambda: annualised_volatility(r, periods_per_year=252),
        lambda: sharpe_ratio(r, periods_per_year=252, se_method=SharpeSE.IID_NORMAL),
        lambda: tracking_error(r, r * 0.5, periods_per_year=252),
    ):
        with pytest.raises(ValidationError, match="dates are monthly"):
            call()


def test_a_risk_report_with_a_contradicting_value_fails(tmp_path: Path) -> None:
    from qrlab.experiments import run_experiment
    from qrlab.experiments.kinds import KINDS

    root = Path(__file__).parents[3]
    text = (root / "configs" / "experiments" / "example_risk_report.toml").read_text("utf-8")
    examples = (root / "examples" / "data").as_posix()
    text = text.replace("periods_per_year = 12", "periods_per_year = 252")
    text = text.replace("../../examples/data", examples).replace(
        "../../results/example-risk-report", (tmp_path / "out").as_posix()
    )
    config = tmp_path / "risk.toml"
    config.write_text(text, encoding="utf-8")
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "periods_per_year is 252, but the dates are monthly" in result.record["error"]
