"""Concentration, cost and data-quality checks: one triggering and one passing case each.

Hand values (design note): weights 0.5 / 0.3 / 0.2 give largest 0.5, top-5 1.0, HHI 0.38
(effective positions 2.6316); TER 0.20 % and 0.15 % at weights 0.54 and 0.36 with 10 % cash
give 0.162 %; the toy portfolio's trading drag is 20 / mean(values) x 365 / 88.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

import pytest

from qrlab.checks import concentration, costs, data_quality
from qrlab.checks.context import CheckContext
from qrlab.checks.framework import Measurement, NotApplicable
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.master import InstrumentType
from support.checks import AS_OF, A, B, C, fund, weighted_context
from support.portfolio import D3, EUR, FixedRates, eur_only, toy_setup

USD = Currency("USD")
NO_PARAMS: Mapping[str, object] = {}


def _one(outcome: list[Measurement] | NotApplicable) -> Measurement:
    assert not isinstance(outcome, NotApplicable), outcome
    (measurement,) = outcome
    return measurement


# --------------------------------------------------------------------------- concentration
def test_concentration_hand_example() -> None:
    ctx = weighted_context({A: "0.5", B: "0.3", C: "0.2"})
    assert _one(concentration.largest_position(ctx, NO_PARAMS)).observed == pytest.approx(0.5)
    assert _one(concentration.top5(ctx, NO_PARAMS)).observed == pytest.approx(1.0)
    hhi = _one(concentration.herfindahl(ctx, NO_PARAMS))
    assert hhi.observed == pytest.approx(0.38)
    assert hhi.details["effective_positions"] == "2.6316"


def test_concentration_passing_portfolio_and_cash_only() -> None:
    ctx = weighted_context({A: "0.1", B: "0.1", C: "0.1"})  # 70 % cash
    assert _one(concentration.largest_position(ctx, NO_PARAMS)).observed == pytest.approx(0.1)
    assert _one(concentration.herfindahl(ctx, NO_PARAMS)).observed == pytest.approx(0.03)
    cash_only = weighted_context({})
    for check in (concentration.largest_position, concentration.top5, concentration.herfindahl):
        assert isinstance(check(cash_only, NO_PARAMS), NotApplicable)


def test_foreign_currency_exposure() -> None:
    rates = FixedRates({AS_OF: "1.25"})
    ctx = weighted_context(
        {A: "0.3", B: "0.6"},
        currencies={A: USD},
        to_base=rates,
        instruments={A: fund(A, currency=USD), B: fund(B)},
    )
    measured = _one(concentration.foreign_currency(ctx, NO_PARAMS))
    assert measured.observed == pytest.approx(0.3)
    assert measured.details == {"currency": "USD"}
    hedged = weighted_context(
        {A: "0.3", B: "0.6"},
        currencies={A: USD},
        to_base=rates,
        instruments={A: fund(A, currency=USD, hedged_to=EUR), B: fund(B)},
    )
    assert _one(concentration.foreign_currency(hedged, NO_PARAMS)).observed == 0.0


# --------------------------------------------------------------------------- costs
def test_weighted_ter_hand_example() -> None:
    ctx = weighted_context(
        {A: "0.54", B: "0.36"},
        instruments={A: fund(A, ter=Decimal("0.0020")), B: fund(B, ter=Decimal("0.0015"))},
    )
    measured = _one(costs.weighted_ter(ctx, NO_PARAMS))
    assert measured.observed == pytest.approx(0.00162)
    assert measured.details["excluded_weight"] == "0.000000"


def test_unknown_ter_is_excluded_not_zero() -> None:
    ctx = weighted_context({A: "0.5", B: "0.5"}, instruments={A: fund(A, ter=None), B: fund(B)})
    measured = _one(costs.weighted_ter(ctx, NO_PARAMS))
    assert measured.observed == pytest.approx(0.5 * 0.002)
    assert measured.details["excluded_weight"] == "0.500000"
    nothing = weighted_context({A: "1"}, instruments={})
    assert isinstance(costs.weighted_ter(nothing, NO_PARAMS), NotApplicable)


def test_stocks_have_no_ter() -> None:
    stock = fund(
        A,
        instrument_type=InstrumentType.STOCK,
        replication=None,
        distribution=None,
        ter=None,
        fund_size=None,
    )
    ctx = weighted_context({A: "0.5", B: "0.5"}, instruments={A: stock, B: fund(B)})
    measured = _one(costs.weighted_ter(ctx, NO_PARAMS))
    assert measured.observed == pytest.approx(0.001)
    assert measured.details["excluded_weight"] == "0.000000"


def _toy_context() -> CheckContext:
    history, valuation = toy_setup()
    return CheckContext(
        as_of=D3, history=history, valuation=valuation, to_base=eur_only, instruments={},
        prices={}, portfolio_returns=None, benchmark_returns=None, target_weights=None,
    )  # fmt: skip


def test_trading_drag_hand_example() -> None:
    ctx = _toy_context()
    average = (9990 + 15490 + 15290 + 15480) / 4
    assert _one(costs.trading_drag(ctx, NO_PARAMS)).observed == pytest.approx(
        20 / average * 365 / 88
    )
    assert isinstance(costs.trading_drag(weighted_context({A: "1"}), NO_PARAMS), NotApplicable)


def test_total_cost_adds_ter_and_drag() -> None:
    history, valuation = toy_setup()
    from support.portfolio import X

    ctx = CheckContext(
        as_of=D3, history=history, valuation=valuation, to_base=eur_only, instruments={X: fund(X)},
        prices={}, portfolio_returns=None, benchmark_returns=None, target_weights=None,
    )  # fmt: skip
    measured = _one(costs.total_cost(ctx, NO_PARAMS))
    ter = 2700 / 15480 * 0.002
    drag = 20 / ((9990 + 15490 + 15290 + 15480) / 4) * 365 / 88
    assert measured.observed == pytest.approx(ter + drag)
    assert isinstance(costs.total_cost(_toy_context(), NO_PARAMS), NotApplicable)  # TER unknown


# --------------------------------------------------------------------------- data quality
def test_clean_portfolio_has_no_data_quality_issues() -> None:
    ctx = weighted_context({A: "0.5", B: "0.5"})
    assert _one(data_quality.stale_prices(ctx, NO_PARAMS)).observed == 0
    assert isinstance(data_quality.stale_fx(ctx, NO_PARAMS), NotApplicable)  # plain converter
    assert _one(data_quality.stale_master(ctx, {"max_age_days": 365})).observed == 0
    assert _one(data_quality.missing_master(ctx, NO_PARAMS)).observed == 0
    assert _one(data_quality.pnl_residual(ctx, NO_PARAMS)).observed == 0


def test_missing_and_stale_master_data() -> None:
    ctx = weighted_context(
        {A: "0.5", B: "0.5"},
        instruments={A: fund(A, as_of=date(2024, 1, 1), ter=None)},  # B has no record at all
    )
    missing = _one(data_quality.missing_master(ctx, NO_PARAMS))
    assert missing.observed == 2
    assert f"{B.code}:record" in missing.details["missing"]
    assert f"{A.code}:ter" in missing.details["missing"]
    assert _one(data_quality.stale_master(ctx, {"max_age_days": 365})).observed == 1
    with pytest.raises(ValidationError, match="max_age_days"):
        data_quality.stale_master(ctx, {"max_age_days": "365"})


def test_stale_prices_and_fx_on_the_check_date() -> None:
    from qrlab.portfolio.valuation import EcbConverter, value_portfolio
    from support.portfolio import D0, X, price_series, synthetic_fx

    history, _ = toy_setup()
    later = date(2026, 4, 2)
    prices = {X: price_series({D0: 50.0, D3: 54.0})}
    valuation = value_portfolio(history, prices, eur_only, dates=[D3, later], max_price_age_days=5)
    stale_fx = EcbConverter(synthetic_fx({D0: {"USD": 1.25}}), base=EUR, max_age_days=400)
    stale_fx(Money.of(1, "USD"), later)
    ctx = CheckContext(
        as_of=later, history=history, valuation=valuation, to_base=stale_fx, instruments={},
        prices=prices, portfolio_returns=None, benchmark_returns=None, target_weights=None,
    )  # fmt: skip
    measured = _one(data_quality.stale_prices(ctx, NO_PARAMS))
    assert measured.observed == 1
    assert measured.details["instruments"] == f"{X.code} (2026-03-31)"
    assert _one(data_quality.stale_fx(ctx, NO_PARAMS)).observed == 1


def test_residual_with_a_wrong_converter() -> None:
    from support.portfolio import multi_currency_setup

    history, valuation, _ = multi_currency_setup()
    wrong = FixedRates({date(2026, 1, 2): "1.25"})
    ctx = CheckContext(
        as_of=D3, history=history, valuation=valuation, to_base=wrong, instruments={}, prices={},
        portfolio_returns=None, benchmark_returns=None, target_weights=None,
    )  # fmt: skip
    assert _one(data_quality.pnl_residual(ctx, NO_PARAMS)).observed > 1


# --------------------------------------------------------------------------- context validation
def test_context_validation() -> None:
    ctx = weighted_context({A: "1"})
    with pytest.raises(ValidationError, match="valuation date"):
        CheckContext(**{**ctx.__dict__, "as_of": date(2026, 7, 1)})
    with pytest.raises(ValidationError, match="target weights"):
        CheckContext(**{**ctx.__dict__, "target_weights": {A.code: 0.5}})


def test_context_edge_cases() -> None:
    from qrlab.portfolio.ledger import replay
    from qrlab.portfolio.valuation import value_portfolio

    empty_history = replay([], base=EUR, to_base=eur_only)
    zero = value_portfolio(empty_history, {}, eur_only, dates=[AS_OF], max_price_age_days=0)
    with pytest.raises(ValidationError, match="positive"):
        CheckContext(
            as_of=AS_OF, history=empty_history, valuation=zero, to_base=eur_only, instruments={},
            prices={}, portfolio_returns=None, benchmark_returns=None, target_weights=None,
        )  # fmt: skip
    ok = weighted_context({A: "0.6"}, target_weights={A.code: 0.5, "cash": 0.5})
    assert ok.target_weights == {A.code: 0.5, "cash": 0.5}
    no_master = weighted_context({A: "0.3", B: "0.3"}, instruments={})
    assert no_master.exposure_currency(B) == EUR
