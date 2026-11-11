"""Inputs of the health checks and shared portfolio quantities (weights, exposures)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import Instrument
from qrlab.lookthrough.inputs import LookThroughInputs
from qrlab.portfolio.ledger import LedgerHistory, ToBase
from qrlab.portfolio.valuation import PriceSeries, Valuation

__all__ = ["CASH", "CheckContext"]

CASH = "cash"
"""Key for cash in target weights."""


@dataclass(frozen=True)
class CheckContext:
    """Everything a check may read. Optional inputs are ``None`` when not available.

    Parameters
    ----------
    as_of
        Date of the checks; must be a valuation date.
    history, valuation, to_base
        Ledger history, its valuation and the converter used for them.
    instruments
        Master data by ISIN (missing entries are themselves a data-quality finding).
    prices
        Price series by ISIN, for return-based checks.
    portfolio_returns
        Portfolio return series at a regular frequency (e.g. monthly TWR), or ``None``.
    benchmark_returns
        Benchmark returns with the same index as ``portfolio_returns``, or ``None``.
    target_weights
        Target weights by ISIN code and ``"cash"``, summing to 1, or ``None``.
    lookthrough
        Exposures through fund holdings on ``as_of``, with the holdings and tracking series,
        or ``None``.
    """

    as_of: date
    history: LedgerHistory
    valuation: Valuation
    to_base: ToBase
    instruments: Mapping[Isin, Instrument]
    prices: Mapping[Isin, PriceSeries]
    portfolio_returns: pd.Series | None
    benchmark_returns: pd.Series | None
    target_weights: Mapping[str, float] | None
    lookthrough: LookThroughInputs | None

    def __post_init__(self) -> None:
        """Validate the date and the target weights."""
        if self.as_of not in self.valuation.totals:
            raise ValidationError(f"as_of {self.as_of} is not a valuation date")
        if self.valuation.totals[self.as_of] <= 0:
            raise ValidationError("checks need a positive portfolio value on as_of")
        if self.lookthrough is not None:
            dated = self.lookthrough.exposures.as_of
            if dated != self.as_of:
                raise ValidationError(f"look-through is as of {dated}, checks as of {self.as_of}")
        if self.target_weights is not None:
            total = sum(self.target_weights.values())
            if abs(total - 1.0) > 1e-9 or any(w < 0 for w in self.target_weights.values()):
                raise ValidationError(
                    f"target weights must be non-negative and sum to 1 (sum {total}); not rescaled"
                )

    @property
    def base(self) -> Currency:
        """Base currency."""
        return self.history.base

    @property
    def total(self) -> float:
        """Total portfolio value on ``as_of`` in the base currency, including cash."""
        return float(self.valuation.totals[self.as_of])

    def position_weights(self) -> dict[Isin, float]:
        """Weights by ISIN (summed across accounts) over the total value including cash."""
        weights: dict[Isin, float] = {}
        for (_, isin), value in self.valuation.positions[self.as_of].items():
            weights[isin] = weights.get(isin, 0.0) + float(value) / self.total
        return weights

    def cash_weights(self) -> dict[Currency, float]:
        """Cash weights by currency over the total value."""
        weights: dict[Currency, float] = {}
        for (_, currency), balance in self.history.state_on(self.as_of).cash.items():
            value = float(self.to_base(Money(balance, currency), self.as_of).amount)
            weights[currency] = weights.get(currency, 0.0) + value / self.total
        return weights

    def exposure_currency(self, isin: Isin) -> Currency:
        """Currency a position is exposed to: the hedge currency if hedged, else the fund's."""
        instrument = self.instruments.get(isin)
        if instrument is not None:
            return instrument.hedged_to or instrument.currency
        for (_, held), position in self.history.state_on(self.as_of).positions.items():
            if held == isin:
                return position.currency
        raise ValidationError(f"{isin.code} is not held on {self.as_of}")  # pragma: no cover
