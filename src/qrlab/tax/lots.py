"""Units matched first in, first out, for the holding periods of sales (phases 9.2 and 9.3).

The ledger keeps an average cost (:mod:`qrlab.portfolio.ledger`); some tax rules depend on
how long the units sold were held. Here units are matched first in, first out per account
and instrument: purchases and transfers in add lots, sales and transfers out remove the
oldest first, and a split scales them.
"""

from __future__ import annotations

import calendar
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from qrlab.portfolio.transactions import Transaction, TransactionKind

__all__ = ["FifoSale", "add_months", "fifo_sales"]

_K = TransactionKind


@dataclass(frozen=True)
class FifoSale:
    """A sale and the lots it took: ``(acquisition date, units)``, oldest first."""

    sold: date
    account: str
    isin: str
    quantity: Decimal
    lots: tuple[tuple[date, Decimal], ...]

    @property
    def latest_acquisition(self) -> date:
        """The acquisition date of the youngest units sold."""
        return max(day for day, _ in self.lots) if self.lots else date.min

    def units_held(self, months: int) -> Decimal:
        """Units sold that were held at least ``months`` calendar months."""
        return sum(
            (units for day, units in self.lots if add_months(day, months) <= self.sold),
            Decimal(0),
        )


def add_months(day: date, months: int) -> date:
    """Return ``day`` plus calendar ``months`` (the 31st becomes the month's last day)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


@dataclass
class _Lot:
    day: date
    units: Decimal


def fifo_sales(transactions: Iterable[Transaction]) -> tuple[FifoSale, ...]:
    """Return every sale (not transfer out) with the lots it took, first in, first out."""
    lots: dict[tuple[str, str], deque[_Lot]] = {}
    out = []
    for t in transactions:
        if t.isin is None or t.quantity is None:
            continue
        queue = lots.setdefault((t.account, t.isin.code), deque())
        if t.kind in (_K.BUY, _K.TRANSFER_IN):
            queue.append(_Lot(t.trade_date, t.quantity))
        elif t.kind is _K.SPLIT:
            for lot in queue:
                lot.units *= t.quantity
        else:  # with a quantity and an instrument, only sales and transfers out are left
            needed, taken = t.quantity, []
            while needed > 0 and queue:
                lot = queue[0]
                take = min(lot.units, needed)
                taken.append((lot.day, take))
                lot.units -= take
                needed -= take
                if lot.units == 0:
                    queue.popleft()
            if t.kind is _K.SELL:
                out.append(FifoSale(t.trade_date, t.account, t.isin.code, t.quantity, tuple(taken)))
    return tuple(out)
