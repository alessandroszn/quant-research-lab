"""Replay of transactions into positions, cash per currency and cost basis.

Rules:

- transactions must be in non-decreasing date order; same-day transactions are applied in the
  given order (e.g. a deposit before the purchase it funds);
- impossible states raise: selling or transferring out more than is held, income or splits on
  a position not held, negative cash (unless explicitly allowed for margin accounts);
- cost basis is the **weighted average cost including purchase fees and taxes**, kept in the
  base currency at the conversion rate of each purchase date (as the Italian "costo medio
  ponderato") and, for same-currency charges, in the instrument currency;
- every amount converted to the base currency goes through the caller's explicit ``to_base``
  converter, which must return base-currency ``Money``;
- an FX conversion executed at a rate different from the converter's reference rate books the
  difference (the spread) as a cost, so that the profit and loss reconciles.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import TypeVar

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.transactions import Transaction, TransactionKind

__all__ = [
    "CashMovement",
    "Cost",
    "ExternalFlow",
    "Income",
    "LedgerHistory",
    "LedgerState",
    "Position",
    "RealisedGain",
    "ToBase",
    "replay",
]

_T = TypeVar("_T")

ToBase = Callable[[Money, date], Money]
"""Converts an amount to the base currency at the rate of a given date."""

PositionKey = tuple[str, Isin]
CashKey = tuple[str, Currency]
K = TransactionKind


@dataclass(frozen=True)
class Position:
    """Units held and their cost basis."""

    quantity: Decimal
    currency: Currency
    cost_local: Money
    cost_base: Decimal

    @property
    def average_cost_base(self) -> Decimal:
        """Average cost per unit in the base currency (fees included)."""
        return self.cost_base / self.quantity


@dataclass(frozen=True)
class LedgerState:
    """Read-only positions and cash balances after a date's transactions."""

    positions: Mapping[PositionKey, Position]
    cash: Mapping[CashKey, Decimal]


@dataclass(frozen=True)
class RealisedGain:
    """Gain realised by a sale, in the base currency (and gross figures in local currency)."""

    trade_date: date
    account: str
    isin: Isin
    quantity: Decimal
    proceeds_base: Decimal
    cost_base: Decimal
    gain_base: Decimal
    proceeds_local: Money
    cost_local: Money


@dataclass(frozen=True)
class ExternalFlow:
    """Money or securities entering (+) or leaving (-) the portfolio, in the base currency."""

    trade_date: date
    account: str
    kind: TransactionKind
    amount_base: Decimal


@dataclass(frozen=True)
class Income:
    """Dividend or interest, in the base currency."""

    trade_date: date
    account: str
    kind: TransactionKind
    isin: Isin | None
    gross_base: Decimal
    taxes_base: Decimal
    fees_base: Decimal

    @property
    def net_base(self) -> Decimal:
        """Gross income minus withheld taxes and fees."""
        return self.gross_base - self.taxes_base - self.fees_base


@dataclass(frozen=True)
class Cost:
    """A cost not included in a cost basis (standalone fees and taxes, conversion fees, ...)."""

    trade_date: date
    account: str
    kind: TransactionKind
    amount_base: Decimal


@dataclass(frozen=True)
class CashMovement:
    """A change of a cash balance in its own currency (used for the currency effect on cash)."""

    trade_date: date
    account: str
    currency: Currency
    amount: Decimal


@dataclass(frozen=True)
class LedgerHistory:
    """Result of :func:`replay`: states after each trade date and booked events."""

    base: Currency
    dates: tuple[date, ...]
    states: tuple[LedgerState, ...]
    realised: tuple[RealisedGain, ...]
    external_flows: tuple[ExternalFlow, ...]
    income: tuple[Income, ...]
    costs: tuple[Cost, ...]
    cash_movements: tuple[CashMovement, ...]

    def state_on(self, day: date) -> LedgerState:
        """State after all transactions dated on or before ``day`` (empty before the first)."""
        position = bisect.bisect_right(self.dates, day)
        if position == 0:
            return LedgerState(MappingProxyType({}), MappingProxyType({}))
        return self.states[position - 1]


def replay(
    transactions: Iterable[Transaction],
    *,
    base: Currency,
    to_base: ToBase,
    allow_negative_cash: bool = False,
) -> LedgerHistory:
    """Apply transactions in order and return the resulting history.

    Parameters
    ----------
    transactions
        In non-decreasing date order, with unique ids.
    base
        Base currency of the cost basis and of all ``*_base`` amounts.
    to_base
        Converter to ``base`` at a date's rate (explicit; e.g. dated ECB rates).
    allow_negative_cash
        Allow negative cash balances (margin). Off by default: negative cash raises.
    """
    return _Replayer(base, to_base, allow_negative_cash).run(list(transactions))


class _Replayer:
    def __init__(self, base: Currency, to_base: ToBase, allow_negative_cash: bool) -> None:
        self.base = base
        self.to_base_fn = to_base
        self.allow_negative_cash = allow_negative_cash
        self.positions: dict[PositionKey, Position] = {}
        self.cash: dict[CashKey, Decimal] = {}
        self.realised: list[RealisedGain] = []
        self.flows: list[ExternalFlow] = []
        self.income: list[Income] = []
        self.costs: list[Cost] = []
        self.movements: list[CashMovement] = []
        self.dates: list[date] = []
        self.states: list[LedgerState] = []

    def run(self, transactions: list[Transaction]) -> LedgerHistory:
        seen: set[str] = set()
        for i, t in enumerate(transactions):
            if t.id in seen:
                raise ValidationError(f"duplicated transaction id {t.id!r}")
            seen.add(t.id)
            if i and t.trade_date < transactions[i - 1].trade_date:
                raise ValidationError(f"{t.id}: transactions must be in date order")
            self._apply(t)
            last_of_day = (
                i == len(transactions) - 1 or transactions[i + 1].trade_date != t.trade_date
            )
            if last_of_day:
                self.dates.append(t.trade_date)
                self.states.append(
                    LedgerState(
                        MappingProxyType(dict(self.positions)), MappingProxyType(dict(self.cash))
                    )
                )
        return LedgerHistory(
            base=self.base,
            dates=tuple(self.dates),
            states=tuple(self.states),
            realised=tuple(self.realised),
            external_flows=tuple(self.flows),
            income=tuple(self.income),
            costs=tuple(self.costs),
            cash_movements=tuple(self.movements),
        )

    # ----------------------------------------------------------------- helpers
    def conv(self, amount: Money, day: date) -> Decimal:
        return _base_amount(self.to_base_fn(amount, day), self.base)

    def move_cash(self, t: Transaction, amount: Money, sign: int) -> None:
        # Callers never pass zero: Transaction validation makes amounts positive and charges
        # are only moved when non-zero.
        key = (t.account, amount.currency)
        self.cash[key] = self.cash.get(key, Decimal(0)) + sign * amount.amount
        self.movements.append(
            CashMovement(t.trade_date, t.account, amount.currency, sign * amount.amount)
        )

    def check_cash(self, t: Transaction) -> None:
        if self.allow_negative_cash:
            return
        for (account, currency), balance in self.cash.items():
            if account == t.account and balance < 0:
                raise ValidationError(
                    f"{t.id}: negative cash {balance} {currency} in account {account!r}"
                )

    def charges(self, t: Transaction) -> tuple[Decimal, list[Money]]:
        """Debit fees and taxes from cash; return their base value and the amounts."""
        total = Decimal(0)
        for charge in (t.fees, t.taxes):
            if charge.amount:
                self.move_cash(t, charge, -1)
                total += self.conv(charge, t.trade_date)
        return total, [c for c in (t.fees, t.taxes) if c.amount]

    def held(self, t: Transaction) -> Position:
        position = self.positions.get((t.account, _isin(t)))
        if position is None:
            raise ValidationError(f"{t.id}: {_isin(t)} is not held in account {t.account!r}")
        return position

    # ----------------------------------------------------------------- apply
    def _apply(self, t: Transaction) -> None:
        handler = {
            K.DEPOSIT: self._deposit,
            K.WITHDRAWAL: self._withdrawal,
            K.BUY: self._buy,
            K.SELL: self._sell,
            K.DIVIDEND: self._income,
            K.INTEREST: self._income,
            K.FEE: self._cost,
            K.TAX: self._cost,
            K.FX_CONVERSION: self._fx,
            K.TRANSFER_IN: self._transfer_in,
            K.TRANSFER_OUT: self._transfer_out,
            K.SPLIT: self._split,
        }[t.kind]
        handler(t)
        self.check_cash(t)

    def _deposit(self, t: Transaction) -> None:
        self.move_cash(t, _amount(t), +1)
        self.flows.append(
            ExternalFlow(t.trade_date, t.account, t.kind, self.conv(_amount(t), t.trade_date))
        )
        self._standalone_charges(t)

    def _withdrawal(self, t: Transaction) -> None:
        self.move_cash(t, _amount(t), -1)
        self.flows.append(
            ExternalFlow(t.trade_date, t.account, t.kind, -self.conv(_amount(t), t.trade_date))
        )
        self._standalone_charges(t)

    def _standalone_charges(self, t: Transaction) -> None:
        total, _ = self.charges(t)
        if total:
            self.costs.append(Cost(t.trade_date, t.account, t.kind, total))

    def _cost(self, t: Transaction) -> None:
        self.move_cash(t, _amount(t), -1)
        total, _ = self.charges(t)
        self.costs.append(
            Cost(t.trade_date, t.account, t.kind, self.conv(_amount(t), t.trade_date) + total)
        )

    def _fx(self, t: Transaction) -> None:
        self.move_cash(t, _amount(t), -1)
        self.move_cash(t, _fx_counter(t), +1)
        # The spread between the executed rate and the reference rate of ``to_base`` is a cost
        # (positive when less value is received than given up); without it the P&L would not
        # reconcile.
        spread = self.conv(_amount(t), t.trade_date) - self.conv(_fx_counter(t), t.trade_date)
        if spread:
            self.costs.append(Cost(t.trade_date, t.account, K.FX_CONVERSION, spread))
        self._standalone_charges(t)

    def _income(self, t: Transaction) -> None:
        if t.kind is K.DIVIDEND:
            self.held(t)
        self.move_cash(t, _amount(t), +1)
        gross = self.conv(_amount(t), t.trade_date)
        fees = self.conv(t.fees, t.trade_date) if t.fees.amount else Decimal(0)
        taxes = self.conv(t.taxes, t.trade_date) if t.taxes.amount else Decimal(0)
        self.charges(t)
        self.income.append(Income(t.trade_date, t.account, t.kind, t.isin, gross, taxes, fees))

    def _buy(self, t: Transaction) -> None:
        gross = Money(_quantity(t) * _price(t).amount, _price(t).currency)
        self.move_cash(t, gross, -1)
        charges_base, charges = self.charges(t)
        local_charges = sum((c.amount for c in charges if c.currency == gross.currency), Decimal(0))
        self._add_units(
            t, _quantity(t), gross, local_charges, self.conv(gross, t.trade_date) + charges_base
        )

    def _transfer_in(self, t: Transaction) -> None:
        value = Money(_quantity(t) * _price(t).amount, _price(t).currency)
        value_base = self.conv(value, t.trade_date)
        self._add_units(t, _quantity(t), value, Decimal(0), value_base)
        self.flows.append(ExternalFlow(t.trade_date, t.account, t.kind, value_base))
        self._standalone_charges(t)

    def _add_units(
        self,
        t: Transaction,
        quantity: Decimal,
        gross: Money,
        local_charges: Decimal,
        cost_base: Decimal,
    ) -> None:
        key = (t.account, _isin(t))
        current = self.positions.get(key)
        cost_local = Money(gross.amount + local_charges, gross.currency)
        if current is None:
            self.positions[key] = Position(quantity, gross.currency, cost_local, cost_base)
            return
        if current.currency != gross.currency:
            raise ValidationError(
                f"{t.id}: {_isin(t)} is held in {current.currency}, not {gross.currency}"
            )
        self.positions[key] = Position(
            current.quantity + quantity,
            current.currency,
            current.cost_local + cost_local,
            current.cost_base + cost_base,
        )

    def _remove_units(self, t: Transaction) -> tuple[Position, Decimal, Money]:
        """Remove units at average cost; return the old position and the removed cost."""
        position = self.positions.get((t.account, _isin(t)))
        if position is None or _quantity(t) > position.quantity:
            held = Decimal(0) if position is None else position.quantity
            raise ValidationError(
                f"{t.id}: cannot remove {_quantity(t)} units, more than {held} held"
            )
        share_base = position.cost_base * _quantity(t) / position.quantity
        share_local = Money(
            position.cost_local.amount * _quantity(t) / position.quantity, position.currency
        )
        remaining = position.quantity - _quantity(t)
        if remaining == 0:
            del self.positions[(t.account, _isin(t))]
        else:
            self.positions[(t.account, _isin(t))] = Position(
                remaining,
                position.currency,
                position.cost_local - share_local,
                position.cost_base - share_base,
            )
        return position, share_base, share_local

    def _sell(self, t: Transaction) -> None:
        _, cost_base, cost_local = self._remove_units(t)
        gross = Money(_quantity(t) * _price(t).amount, _price(t).currency)
        self.move_cash(t, gross, +1)
        charges_base, charges = self.charges(t)
        local_charges = sum((c.amount for c in charges if c.currency == gross.currency), Decimal(0))
        proceeds_base = self.conv(gross, t.trade_date) - charges_base
        self.realised.append(
            RealisedGain(
                trade_date=t.trade_date,
                account=t.account,
                isin=_isin(t),
                quantity=_quantity(t),
                proceeds_base=proceeds_base,
                cost_base=cost_base,
                gain_base=proceeds_base - cost_base,
                proceeds_local=Money(gross.amount - local_charges, gross.currency),
                cost_local=cost_local,
            )
        )

    def _transfer_out(self, t: Transaction) -> None:
        self._remove_units(t)
        value = Money(_quantity(t) * _price(t).amount, _price(t).currency)
        self.flows.append(
            ExternalFlow(t.trade_date, t.account, t.kind, -self.conv(value, t.trade_date))
        )
        self._standalone_charges(t)

    def _split(self, t: Transaction) -> None:
        position = self.held(t)
        self.positions[(t.account, _isin(t))] = Position(
            position.quantity * _quantity(t),
            position.currency,
            position.cost_local,
            position.cost_base,
        )


# --------------------------------------------------------------------------- field accessors
def _base_amount(converted: object, base: Currency) -> Decimal:
    if not isinstance(converted, Money) or converted.currency != base:
        raise ValidationError(f"to_base must return Money in the base currency {base}")
    return converted.amount


def _required(value: _T | None, t: Transaction, name: str) -> _T:
    if value is None:  # pragma: no cover - guaranteed by Transaction validation
        raise ValidationError(f"{t.id}: missing {name}")
    return value


def _isin(t: Transaction) -> Isin:
    return _required(t.isin, t, "isin")


def _quantity(t: Transaction) -> Decimal:
    return _required(t.quantity, t, "quantity")


def _price(t: Transaction) -> Money:
    return _required(t.price, t, "price")


def _amount(t: Transaction) -> Money:
    return _required(t.amount, t, "amount")


def _fx_counter(t: Transaction) -> Money:
    return _required(t.fx_counter, t, "fx_counter")
