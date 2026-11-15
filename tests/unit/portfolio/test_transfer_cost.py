"""Transfers in with an original cost (design 8.8, deviation approved 2026-11-15), by hand.

A starting position: on D0, 1,000 EUR is deposited and 100 units of X come in at a market price
of 50, with an original cost of 40 per unit. On D1, X is at 55 and 50 units are sold at 55.

- Cost basis 4,000; external flows 1,000 + 5,000 (market value, not cost).
- The gain carried in is 5,000 - 4,000 = 1,000: it accrued before the portfolio was measured.
- Values: D0 6,000; D1 1,000 + 2,750 + 50 x 55 = 6,500. TWR: 0 on D0, 6,500 / 6,000 - 1 on D1.
- Sale: proceeds 2,750, cost 2,000, realised 750. Unrealised on D1: 2,750 - 2,000 = 750.
- P&L since inception: 6,500 - 6,000 = 500 = 750 + 750 - 1,000 (the gain carried in).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest

from qrlab.core.errors import ValidationError
from qrlab.portfolio.ledger import TransferGain, replay
from qrlab.portfolio.performance import (
    FlowTiming,
    contribution_by_position,
    external_flows_by_date,
    pnl_breakdown,
    time_weighted_returns,
)
from qrlab.portfolio.transactions import TransactionKind
from qrlab.portfolio.valuation import value_portfolio
from support.portfolio import D0, D1, EUR, FixedRates, X, Y, eur_only, money, price_series, tx

K = TransactionKind


def _d(*values: int) -> tuple[Decimal, ...]:
    return tuple(Decimal(v) for v in values)


def _start(cost: str | None = "40") -> list:  # type: ignore[type-arg]
    return [
        tx("d", D0, K.DEPOSIT, amount=money(1000)),
        tx(
            "i",
            D0,
            K.TRANSFER_IN,
            isin=X,
            quantity="100",
            price=money(50),
            cost=None if cost is None else money(cost),
        ),
        tx("s", D1, K.SELL, isin=X, quantity="50", price=money(55)),
    ]


def _setup(cost: str | None = "40"):  # type: ignore[no-untyped-def]
    history = replay(_start(cost), base=EUR, to_base=eur_only)
    prices = {X: price_series({D0: 50.0, D1: 55.0})}
    valuation = value_portfolio(history, prices, eur_only, dates=[D0, D1], max_price_age_days=0)
    return history, valuation


def test_the_cost_basis_is_the_original_cost_and_the_flow_the_market_value() -> None:
    history = replay(_start()[:2], base=EUR, to_base=eur_only)
    position = history.state_on(D0).positions[("main", X)]
    assert position.cost_base == Decimal(4000)
    assert position.cost_local == money(4000)
    assert [f.amount_base for f in history.external_flows] == [Decimal(1000), Decimal(5000)]
    assert history.transfers == (TransferGain(D0, "main", X, K.TRANSFER_IN, Decimal(1000)),)


def test_twr_does_not_see_the_gain_carried_in() -> None:
    history, valuation = _setup()
    result = time_weighted_returns(
        valuation, external_flows_by_date(history), flow_timing=FlowTiming.START_OF_DAY
    )
    assert result.returns.tolist() == pytest.approx([0.0, float(Fraction(1, 12))], abs=1e-15)


def test_realised_and_pnl_by_hand() -> None:
    history, valuation = _setup()
    (gain,) = history.realised
    assert (gain.proceeds_base, gain.cost_base, gain.gain_base) == _d(2750, 2000, 750)
    pnl = pnl_breakdown(history, valuation, eur_only, start=None, end=D1)
    assert pnl.total == Decimal(500)
    assert pnl.realised == Decimal(750)
    assert pnl.unrealised_change == Decimal(750)
    assert pnl.transfers == Decimal(-1000)
    assert pnl.residual == Decimal(0)
    assert contribution_by_position(history, valuation, eur_only, start=None, end=D1) == {
        ("main", X): Decimal(500)
    }


def test_a_period_after_the_transfer_has_no_transfer_term() -> None:
    history, valuation = _setup()
    pnl = pnl_breakdown(history, valuation, eur_only, start=D0, end=D1)
    # V 6,000 -> 6,500 with no flows: 500 = realised 750 + unrealised (750 - 1,000)
    assert (pnl.total, pnl.transfers, pnl.residual) == _d(500, 0, 0)
    assert contribution_by_position(history, valuation, eur_only, start=D0, end=D1) == {
        ("main", X): Decimal(500)
    }


def test_without_a_cost_nothing_changes() -> None:
    history, valuation = _setup(cost=None)
    (gain,) = history.realised
    assert gain.gain_base == Decimal(250)
    pnl = pnl_breakdown(history, valuation, eur_only, start=None, end=D1)
    assert (pnl.total, pnl.realised, pnl.unrealised_change) == _d(500, 250, 250)
    assert (pnl.transfers, pnl.residual) == _d(0, 0)
    assert history.transfers == (TransferGain(D0, "main", X, K.TRANSFER_IN, Decimal(0)),)


def test_a_transfer_out_reconciles() -> None:
    """Buy 100 at 50; on D1 at 55, 40 units leave at 55: 500 = unrealised 300 + carried 200.

    The units that leave carry 40 x (55 - 50) = 200 of gain out of the portfolio. Before 8.8 it
    stayed in the residual.
    """
    transactions = [
        tx("d", D0, K.DEPOSIT, amount=money(5000)),
        tx("b", D0, K.BUY, isin=X, quantity="100", price=money(50)),
        tx("o", D1, K.TRANSFER_OUT, isin=X, quantity="40", price=money(55)),
    ]
    history = replay(transactions, base=EUR, to_base=eur_only)
    prices = {X: price_series({D0: 50.0, D1: 55.0})}
    valuation = value_portfolio(history, prices, eur_only, dates=[D0, D1], max_price_age_days=0)
    pnl = pnl_breakdown(history, valuation, eur_only, start=None, end=D1)
    assert (pnl.total, pnl.unrealised_change, pnl.transfers, pnl.residual) == _d(500, 300, 200, 0)
    assert history.transfers == (TransferGain(D1, "main", X, K.TRANSFER_OUT, Decimal(200)),)
    assert contribution_by_position(history, valuation, eur_only, start=None, end=D1) == {
        ("main", X): Decimal(500)
    }


def test_a_foreign_cost_is_converted_on_the_transfer_date() -> None:
    """10 Y at USD 50, cost USD 40, at 1 EUR = 1.25 USD: basis 320 EUR, flow 400, carried 80."""
    rates = FixedRates({D0: "1.25"})
    transfer = tx(
        "i", D0, K.TRANSFER_IN, isin=Y, quantity="10", price=money(50, "USD"), cost=money(40, "USD")
    )
    history = replay([transfer], base=EUR, to_base=rates)
    position = history.state_on(D0).positions[("main", Y)]
    assert position.cost_base == Decimal(320)
    assert position.cost_local == money(400, "USD")
    assert history.external_flows[0].amount_base == Decimal(400)
    assert history.transfers[0].gain_base == Decimal(80)


def test_cost_is_validated() -> None:
    transfer = _start()[1]
    with pytest.raises(ValidationError, match="buy must not have cost"):
        tx("b", D0, K.BUY, isin=X, quantity="1", price=money(50), cost=money(40))
    with pytest.raises(ValidationError, match="cost must be positive Money"):
        replace(transfer, cost=money(0))
    with pytest.raises(ValidationError, match="cost must be in the price currency"):
        replace(transfer, cost=money(40, "USD"))
