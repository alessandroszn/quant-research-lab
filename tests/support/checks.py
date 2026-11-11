"""Synthetic portfolios with chosen weights for health-check tests (no real data)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pandas as pd

from qrlab.checks.context import CheckContext
from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import (
    AssetClass,
    Distribution,
    Instrument,
    InstrumentType,
    Replication,
)
from qrlab.lookthrough.inputs import LookThroughInputs
from qrlab.portfolio.ledger import ToBase, replay
from qrlab.portfolio.transactions import TransactionKind
from qrlab.portfolio.valuation import value_portfolio
from support.portfolio import EUR, money, price_series, tx

A, B, C, D, E, F = (
    Isin(code)
    for code in (
        "IE0000000046",
        "IE0000000053",
        "IE0000000061",
        "IE0000000079",
        "LU0000000082",
        "US0000000093",
    )
)
AS_OF = date(2026, 6, 30)
TOTAL = Decimal(10000)


def fund(isin: Isin, **changes: object) -> Instrument:
    """Return a complete, current synthetic ETF record."""
    base = Instrument(
        isin=isin,
        name=f"Synthetic fund {isin.code}",
        instrument_type=InstrumentType.ETF,
        asset_class=AssetClass.EQUITY,
        currency=EUR,
        as_of=date(2026, 6, 1),
        domicile="IE",
        replication=Replication.PHYSICAL_FULL,
        distribution=Distribution.ACCUMULATING,
        ter=Decimal("0.0020"),
        benchmark="Synthetic index",
        hedged_to=None,
        inception=date(2015, 1, 1),
        fund_size=Money.of("1000000000", "EUR"),
        source="synthetic",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def weighted_context(
    weights: Mapping[Isin, str],
    *,
    instruments: Mapping[Isin, Instrument] | None = None,
    currencies: Mapping[Isin, Currency] | None = None,
    to_base: ToBase | None = None,
    portfolio_returns: pd.Series | None = None,
    benchmark_returns: pd.Series | None = None,
    target_weights: Mapping[str, float] | None = None,
    prices: Mapping[Isin, pd.Series] | None = None,
    lookthrough: LookThroughInputs | None = None,
) -> CheckContext:
    """Build a portfolio worth 10,000 bought at price 1 on AS_OF, with the given weights.

    Positions are in EUR unless ``currencies`` says otherwise (then ``to_base`` must convert).
    Remaining weight stays in EUR cash. ``prices`` replaces the flat price-1 series per ISIN.
    """
    currencies = currencies or {}
    convert = to_base or _identity
    transactions = [tx("dep", AS_OF, TransactionKind.DEPOSIT, amount=money(str(TOTAL)))]
    for number, (isin, weight) in enumerate(weights.items()):
        currency = currencies.get(isin, EUR)
        units = TOTAL * Decimal(weight)
        if currency != EUR:
            # weight is in base currency: buy as many foreign units as that value is worth
            units = units / convert(Money(Decimal(1), currency), AS_OF).amount
            cost = convert(Money(units, currency), AS_OF).amount
            transactions.append(
                tx(
                    f"fx{number}",
                    AS_OF,
                    TransactionKind.FX_CONVERSION,
                    amount=money(str(cost)),
                    fx_counter=Money(units, currency),
                )
            )
        transactions.append(
            tx(
                f"buy{number}",
                AS_OF,
                TransactionKind.BUY,
                isin=isin,
                quantity=str(units),
                price=Money(Decimal(1), currency),
            )
        )
    history = replay(transactions, base=EUR, to_base=convert)
    series = {
        isin: price_series({AS_OF: 1.0}, currency=currencies.get(isin, EUR)) for isin in weights
    }
    valuation = value_portfolio(history, series, convert, dates=[AS_OF], max_price_age_days=0)
    if prices is not None:
        from qrlab.data.user_csv import PriceType
        from qrlab.portfolio.valuation import PriceSeries

        series = {
            isin: PriceSeries(p, currencies.get(isin, EUR), PriceType.PRICE)
            for isin, p in prices.items()
        }
    return CheckContext(
        as_of=AS_OF,
        history=history,
        valuation=valuation,
        to_base=convert,
        instruments=instruments if instruments is not None else {i: fund(i) for i in weights},
        prices=series,
        portfolio_returns=portfolio_returns,
        benchmark_returns=benchmark_returns,
        target_weights=target_weights,
        lookthrough=lookthrough,
    )


def _identity(amount: Money, on: date) -> Money:
    assert amount.currency == EUR, amount
    return amount


def isins(count: int) -> Sequence[Isin]:
    """Return the first ``count`` synthetic ISINs."""
    return (A, B, C, D, E, F)[:count]
