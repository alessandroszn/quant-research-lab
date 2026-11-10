"""Transactions and ledger replay. Hand values from docs/design/2.1-portfolio.md.

Toy portfolio (EUR): deposit 10,000; buy 100 X @ 50 with fee 10 (average cost 50.10);
deposit 5,000; dividend 100; sell 50 X @ 54 with fee 10 -> realised 2,700 - 10 - 50 * 50.10 = 185.
Cash after each date: 4,990; 9,990; 10,090; 12,780.

Multi-currency example (EUR base, 1 EUR = 1.25 USD, later 1.60 USD; exact in binary):
deposit EUR 10,000; convert EUR 4,000.80 -> USD 5,001 with fee EUR 2; buy 100 Y @ USD 50 with
fee USD 1 -> cost in EUR 4,000 + 0.80 = 4,000.80; sell 40 Y @ USD 55 with fee USD 1 when
1 EUR = 1.60 USD -> proceeds EUR 1,375, fee EUR 0.625, cost share 1,600.32, realised -225.945.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from qrlab.core.errors import ValidationError
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.transactions import TransactionKind
from support.portfolio import (
    D0,
    D1,
    D2,
    D3,
    EUR,
    USD,
    FixedRates,
    X,
    Y,
    eur_only,
    money,
    toy_transactions,
    tx,
)

K = TransactionKind


# --------------------------------------------------------------------------- toy portfolio
def test_toy_portfolio_cash_and_positions_by_date() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    expected_cash = {D0: "4990", D1: "9990", D2: "10090", D3: "12780"}
    expected_units = {D0: "100", D1: "100", D2: "100", D3: "50"}
    for day, cash in expected_cash.items():
        state = history.state_on(day)
        assert state.cash[("main", EUR)] == Decimal(cash)
        assert state.positions[("main", X)].quantity == Decimal(expected_units[day])


def test_average_cost_includes_buy_fees() -> None:
    state = replay(toy_transactions(), base=EUR, to_base=eur_only).state_on(D0)
    position = state.positions[("main", X)]
    assert position.cost_base == Decimal("5010")
    assert position.average_cost_base == Decimal("50.10")
    assert position.currency == EUR


def test_realised_gain_hand_example() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    (gain,) = history.realised
    assert gain.trade_date == D3
    assert gain.quantity == Decimal(50)
    assert gain.proceeds_base == Decimal(2690)  # 2,700 - fee 10
    assert gain.cost_base == Decimal("2505.00")
    assert gain.gain_base == Decimal("185.00")
    assert history.state_on(D3).positions[("main", X)].cost_base == Decimal("2505.00")


def test_income_and_flows_are_recorded() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    assert [(f.trade_date, f.amount_base) for f in history.external_flows] == [
        (D0, Decimal(10000)),
        (D1, Decimal(5000)),
    ]
    (income,) = history.income
    assert (income.trade_date, income.net_base) == (D2, Decimal(100))


def test_state_before_first_transaction_is_empty() -> None:
    state = replay(toy_transactions(), base=EUR, to_base=eur_only).state_on(date(2025, 12, 31))
    assert state.cash == {}
    assert state.positions == {}


def test_state_between_dates_carries_the_last_state() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    assert history.state_on(date(2026, 1, 15)) == history.state_on(D0)


def test_states_are_immutable_snapshots() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    with pytest.raises(TypeError):
        history.state_on(D0).cash[("main", EUR)] = Decimal(0)  # type: ignore[index]


# --------------------------------------------------------------------------- multi-currency
def _multi() -> list:  # type: ignore[type-arg]
    return [
        tx("m1", D0, K.DEPOSIT, amount=money(10000)),
        tx(
            "m2",
            D0,
            K.FX_CONVERSION,
            amount=money("4000.80"),
            fx_counter=money(5001, "USD"),
            fees=money(2),
        ),
        tx("m3", D0, K.BUY, isin=Y, quantity="100", price=money(50, "USD"), fees=money(1, "USD")),
        tx("m4", D2, K.DIVIDEND, isin=Y, amount=money(20, "USD"), taxes=money(3, "USD")),
        tx("m5", D3, K.SELL, isin=Y, quantity="40", price=money(55, "USD"), fees=money(1, "USD")),
    ]


RATES = FixedRates({D0: "1.25", D3: "1.60"})


def test_multi_currency_cash_balances() -> None:
    history = replay(_multi(), base=EUR, to_base=RATES)
    state = history.state_on(D3)
    assert state.cash[("main", EUR)] == Decimal("5997.20")  # 10,000 - 4,000.80 - 2
    # USD: +5,001 - 5,000 - 1 + 20 - 3 + 2,200 - 1
    assert state.cash[("main", USD)] == Decimal(2216)


def test_multi_currency_cost_and_realised_gain_in_base() -> None:
    history = replay(_multi(), base=EUR, to_base=RATES)
    position_d0 = history.state_on(D0).positions[("main", Y)]
    assert position_d0.cost_base == Decimal("4000.8")
    assert position_d0.cost_local == money("5001", "USD")  # same-currency fee included
    (gain,) = history.realised
    assert gain.proceeds_base == Decimal("1374.375")  # 1,375 - 0.625
    assert gain.cost_base == Decimal("1600.32")
    assert gain.gain_base == Decimal("-225.945")
    assert history.state_on(D3).positions[("main", Y)].cost_base == Decimal("2400.48")


def test_dividend_net_of_withheld_tax_in_base() -> None:
    history = replay(_multi(), base=EUR, to_base=RATES)
    (income,) = history.income
    assert income.gross_base == Decimal(16)  # USD 20 at 1.25
    assert income.taxes_base == Decimal("2.4")
    assert income.net_base == Decimal("13.6")


def test_costs_are_recorded() -> None:
    history = replay(_multi(), base=EUR, to_base=RATES)
    assert [(c.kind, c.amount_base) for c in history.costs] == [
        (K.FX_CONVERSION, Decimal(2)),
    ]


# --------------------------------------------------------------------------- other kinds
def test_split_keeps_total_cost() -> None:
    transactions = [*toy_transactions()[:2], tx("s", D1, K.SPLIT, isin=X, quantity="2")]
    position = replay(transactions, base=EUR, to_base=eur_only).state_on(D1).positions[("main", X)]
    assert position.quantity == Decimal(200)
    assert position.cost_base == Decimal(5010)
    assert position.average_cost_base == Decimal("25.05")


def test_standalone_fee_tax_interest_and_withdrawal() -> None:
    transactions = [
        tx("a", D0, K.DEPOSIT, amount=money(1000)),
        tx("b", D1, K.INTEREST, amount=money("1.50")),
        tx("c", D1, K.FEE, amount=money(2)),
        tx("d", D1, K.TAX, amount=money("0.30")),
        tx("e", D2, K.WITHDRAWAL, amount=money(500)),
    ]
    history = replay(transactions, base=EUR, to_base=eur_only)
    assert history.state_on(D2).cash[("main", EUR)] == Decimal("499.20")
    assert [f.amount_base for f in history.external_flows] == [Decimal(1000), Decimal(-500)]
    assert [c.amount_base for c in history.costs] == [Decimal(2), Decimal("0.30")]


def test_transfers_in_and_out_are_external_flows_at_market_value() -> None:
    transactions = [
        tx("i", D0, K.TRANSFER_IN, isin=X, quantity="10", price=money(40)),
        tx("o", D1, K.TRANSFER_OUT, isin=X, quantity="4", price=money(45)),
    ]
    history = replay(transactions, base=EUR, to_base=eur_only)
    assert [f.amount_base for f in history.external_flows] == [Decimal(400), Decimal(-180)]
    position = history.state_on(D1).positions[("main", X)]
    assert position.quantity == Decimal(6)
    assert position.cost_base == Decimal(240)  # cost basis taken at market value on transfer in
    assert history.realised == ()  # a transfer out is not a sale


def test_accounts_are_separate() -> None:
    transactions = [
        tx("a", D0, K.DEPOSIT, amount=money(100), account="broker-a"),
        tx("b", D0, K.DEPOSIT, amount=money(200), account="broker-b"),
    ]
    state = replay(transactions, base=EUR, to_base=eur_only).state_on(D0)
    assert state.cash == {("broker-a", EUR): Decimal(100), ("broker-b", EUR): Decimal(200)}


def test_position_closed_completely_is_removed() -> None:
    transactions = [
        *toy_transactions(),
        tx("t6", D3, K.SELL, isin=X, quantity="50", price=money(54)),
    ]
    state = replay(transactions, base=EUR, to_base=eur_only).state_on(D3)
    assert ("main", X) not in state.positions


# --------------------------------------------------------------------------- impossible states
@pytest.mark.parametrize(
    ("transactions", "match"),
    [
        (
            [
                tx("a", D0, K.DEPOSIT, amount=money(100)),
                tx("b", D0, K.SELL, isin=X, quantity="1", price=money(1)),
            ],
            "more than",
        ),
        ([tx("a", D0, K.BUY, isin=X, quantity="1", price=money(1))], "negative cash"),
        ([tx("a", D0, K.DIVIDEND, isin=X, amount=money(1))], "not held"),
        ([tx("a", D0, K.SPLIT, isin=X, quantity="2")], "not held"),
        ([tx("a", D0, K.FEE, amount=money(1, "USD"))], "negative cash"),
        ([tx("a", D0, K.TRANSFER_OUT, isin=X, quantity="1", price=money(1))], "more than"),
    ],
    ids=[
        "oversell",
        "negative-cash",
        "dividend-not-held",
        "split-not-held",
        "fee-no-cash",
        "transfer-out",
    ],
)
def test_impossible_states_raise(transactions: list, match: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValidationError, match=match):
        replay(transactions, base=EUR, to_base=RATES)


def test_negative_cash_can_be_allowed_explicitly() -> None:
    transactions = [tx("a", D0, K.BUY, isin=X, quantity="1", price=money(10))]
    state = replay(transactions, base=EUR, to_base=eur_only, allow_negative_cash=True).state_on(D0)
    assert state.cash[("main", EUR)] == Decimal(-10)


def test_unsorted_dates_and_duplicate_ids_raise() -> None:
    with pytest.raises(ValidationError, match="date order"):
        replay(
            [tx("a", D1, K.DEPOSIT, amount=money(1)), tx("b", D0, K.DEPOSIT, amount=money(1))],
            base=EUR,
            to_base=eur_only,
        )
    with pytest.raises(ValidationError, match="duplicated"):
        replay(
            [tx("a", D0, K.DEPOSIT, amount=money(1)), tx("a", D1, K.DEPOSIT, amount=money(1))],
            base=EUR,
            to_base=eur_only,
        )


def test_converter_must_return_base_currency() -> None:
    def wrong(amount, on):  # type: ignore[no-untyped-def]
        return amount

    with pytest.raises(ValidationError, match="base"):
        replay([tx("a", D0, K.DEPOSIT, amount=money(1, "USD"))], base=EUR, to_base=wrong)


def test_same_day_order_follows_input_order() -> None:
    # buying before the deposit on the same day is impossible; the given order is respected
    buy_first = [
        tx("b", D0, K.BUY, isin=X, quantity="1", price=money(1)),
        tx("a", D0, K.DEPOSIT, amount=money(10)),
    ]
    with pytest.raises(ValidationError, match="negative cash"):
        replay(buy_first, base=EUR, to_base=eur_only)


# --------------------------------------------------------------------------- transaction validation
@pytest.mark.parametrize(
    ("kind", "fields", "match"),
    [
        (K.DEPOSIT, {"isin": X, "amount": money(1)}, "isin"),
        (K.DEPOSIT, {}, "amount"),
        (K.BUY, {"isin": X, "quantity": "1"}, "price"),
        (K.BUY, {"isin": X, "quantity": "0", "price": money(1)}, "quantity"),
        (K.BUY, {"quantity": "1", "price": money(1)}, "isin"),
        (K.SELL, {"isin": X, "quantity": "1", "price": money(-1)}, "price"),
        (K.DIVIDEND, {"isin": X, "amount": money(0)}, "amount"),
        (K.FX_CONVERSION, {"amount": money(1)}, "fx_counter"),
        (K.FX_CONVERSION, {"amount": money(1), "fx_counter": money(1)}, "differ"),
        (K.SPLIT, {"isin": X, "quantity": "2", "price": money(1)}, "price"),
        (K.FEE, {"amount": money(1), "fees": money(-1)}, "fees"),
        (K.INTEREST, {"amount": money(1), "quantity": "1"}, "quantity"),
    ],
)
def test_transaction_validation(kind: TransactionKind, fields: dict, match: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValidationError, match=match):
        tx("x", D0, kind, **fields)


def test_transaction_text_fields_validated() -> None:
    base = tx("x", D0, K.DEPOSIT, amount=money(1))
    with pytest.raises(ValidationError, match="id"):
        replace(base, id=" ")
    with pytest.raises(ValidationError, match="account"):
        replace(base, account="")
    with pytest.raises(ValidationError, match="date"):
        replace(base, trade_date="2026-01-02")  # type: ignore[arg-type]


def test_transaction_flow_classification() -> None:
    assert {k for k in K if k.is_external_flow} == {
        K.DEPOSIT,
        K.WITHDRAWAL,
        K.TRANSFER_IN,
        K.TRANSFER_OUT,
    }


def test_second_purchase_averages_the_cost() -> None:
    # 100 @ 50 + fee 10 (cost 5,010), then 100 @ 60 + fee 10 (cost 6,010): average 55.10
    transactions = [
        *toy_transactions()[:2],
        tx("t3", D1, K.DEPOSIT, amount=money(6010)),
        tx("t4", D1, K.BUY, isin=X, quantity="100", price=money(60), fees=money(10)),
    ]
    position = replay(transactions, base=EUR, to_base=eur_only).state_on(D1).positions[("main", X)]
    assert position.quantity == Decimal(200)
    assert position.average_cost_base == Decimal("55.10")
    assert position.cost_local == money(11020)


def test_same_isin_in_another_currency_raises() -> None:
    transactions = [
        tx("a", D0, K.DEPOSIT, amount=money(1000)),
        tx("b", D0, K.FX_CONVERSION, amount=money(400), fx_counter=money(500, "USD")),
        tx("c", D0, K.BUY, isin=X, quantity="1", price=money(10)),
        tx("d", D0, K.BUY, isin=X, quantity="1", price=money(10, "USD")),
    ]
    with pytest.raises(ValidationError, match="held in EUR"):
        replay(transactions, base=EUR, to_base=RATES)


def test_kind_must_be_enum() -> None:
    with pytest.raises(ValidationError, match="TransactionKind"):
        tx("x", D0, "deposit", amount=money(1))  # type: ignore[arg-type]


def test_fx_conversion_spread_is_a_cost() -> None:
    # EUR 4,000 -> USD 4,950 while the reference rate gives USD 5,000: 4,950 / 1.25 = 3,960,
    # so 40 EUR of value is lost in the conversion.
    transactions = [
        tx("a", D0, K.DEPOSIT, amount=money(10000)),
        tx(
            "b",
            D0,
            K.FX_CONVERSION,
            amount=money(4000),
            fx_counter=money(4950, "USD"),
            fees=money(2),
        ),
    ]
    history = replay(transactions, base=EUR, to_base=RATES)
    assert [(c.kind, c.amount_base) for c in history.costs] == [
        (K.FX_CONVERSION, Decimal(40)),
        (K.FX_CONVERSION, Decimal(2)),
    ]
