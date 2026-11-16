"""Italian stamp duty and IVAFE on financial products: analytics, not tax advice (11.3).

The rules, as checked on 16 November 2026:

- **Imposta di bollo** on the statements of financial products held through an Italian
  intermediary (D.P.R. 642/1972, tariffa parte I, art. 13, comma 2-ter and nota 3-ter): 2 per
  mille a year from 2014 (L. 147/2013, art. 1, comma 581, which also abolished the €34.20
  minimum), on the market value at the end of each statement period (D.M. 24 May 2012, art.
  3), proportional to the days of the period over 365 (circolare 48/E of 21 December 2012),
  rounded to €0.10 (down for a fraction up to €0.05) with a minimum of €1 per statement
  (D.P.R. 642/1972, art. 3). The €14,000 cap concerns clients other than natural persons.
- **IVAFE** on financial products held abroad (D.L. 201/2011, art. 19, commi 18-22): 0.20 % a
  year, 0.40 % in states with a privileged tax regime from 2024 (L. 213/2023, art. 1, comma
  91), on the quoted value on 31 December or at the end of the holding period, proportional to
  the days held and the ownership share, units matched last in, first out; not paid when the
  year's balance is €12 or less (instructions *Redditi PF 2026*, quadro RW).
- **Not computed:** years before 2014 (other rates) and from 2027, when the testo unico
  D.Lgs. 123/2025 applies (art. 205, as moved by D.L. 200/2025, art. 4, comma 5), until its
  articles are checked. Cash (the fixed amounts on current accounts) and the foreign
  wealth-tax credit are not covered.

Here a whole year on yearly statements counts as exactly one year, and the IVAFE divides the
days held by the days of the year, so that a whole year gives the annual rate.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.data.errors import DataNotFoundError
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.ledger import LedgerHistory, ToBase
from qrlab.portfolio.transactions import Transaction, TransactionKind
from qrlab.portfolio.valuation import PriceSeries

__all__ = [
    "FIRST_YEAR",
    "IVAFE_PAYMENT_THRESHOLD",
    "LAST_YEAR",
    "WEALTH_RULES_CHECKED_ON",
    "WEALTH_SOURCES",
    "WEALTH_SOURCES_IT",
    "Custody",
    "HeldLot",
    "Statements",
    "WealthItem",
    "WealthTaxes",
    "WealthYear",
    "Where",
    "lifo_lots",
    "parse_custody",
    "round_stamp_duty",
    "wealth_taxes",
]

WEALTH_RULES_CHECKED_ON = date(2026, 11, 16)
FIRST_YEAR, LAST_YEAR = 2014, 2026
STAMP_RATE = Decimal("0.002")
IVAFE_RATE = Decimal("0.002")
IVAFE_PRIVILEGED_RATE = Decimal("0.004")  # from 2024
IVAFE_PAYMENT_THRESHOLD = Decimal(12)
_PRIVILEGED_FROM = 2024
_CENT, _TEN_CENTS, _HALF_TEN = Decimal("0.01"), Decimal("0.10"), Decimal("0.05")
_K = TransactionKind
WEALTH_SOURCES = (
    "D.P.R. 642/1972, tariffa parte I, art. 13, comma 2-ter and nota 3-ter; art. 3 (stamp duty)",
    "L. 147/2013, art. 1, comma 581 (2 per mille from 2014)",
    "D.M. 24/05/2012, art. 3; Circolare AdE 48/E del 21/12/2012",
    "D.L. 201/2011, art. 19, commi 18-22 (IVAFE); L. 213/2023, art. 1, comma 91 (0.40 %)",
    "Istruzioni Redditi PF 2026, quadro RW (LIFO, days held, €12 threshold)",
    "D.Lgs. 123/2025, art. 205; D.L. 200/2025, art. 4, comma 5 (testo unico from 1/1/2027)",
)
WEALTH_SOURCES_IT = (
    "D.P.R. 642/1972, tariffa parte I, art. 13, comma 2-ter e nota 3-ter; art. 3 (bollo)",
    "L. 147/2013, art. 1, comma 581 (2 per mille dal 2014)",
    "D.M. 24/05/2012, art. 3; Circolare AdE 48/E del 21/12/2012",
    "D.L. 201/2011, art. 19, commi 18-22 (IVAFE); L. 213/2023, art. 1, comma 91 (0,40 %)",
    "Istruzioni Redditi PF 2026, quadro RW (LIFO, giorni di detenzione, soglia di 12 €)",
    "D.Lgs. 123/2025, art. 205; D.L. 200/2025, art. 4, comma 5 (testo unico dal 1/1/2027)",
)


class Where(Enum):
    """Where an account's securities are held, which decides the tax."""

    ITALY = "italy"  # an Italian intermediary: stamp duty
    ABROAD = "abroad"  # IVAFE at 0.20 %
    ABROAD_PRIVILEGED = "abroad_privileged"  # IVAFE at 0.40 % from 2024 (D.M. 4 May 1999 list)


class Statements(Enum):
    """How often an Italian intermediary sends statements (the stamp duty's periods)."""

    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"


@dataclass(frozen=True)
class Custody:
    """One account: where it is held, its statements (Italy) or the owner's share (abroad)."""

    where: Where
    statements: Statements | None
    share: Decimal | None


@dataclass(frozen=True)
class HeldLot:
    """Units of one purchase or transfer in, from ``acquired`` until ``disposed`` (or held).

    ``units`` gives the units from each date on: the first entry is the acquisition, later
    ones follow splits.
    """

    account: str
    isin: Isin
    acquired: date
    disposed: date | None
    units: tuple[tuple[date, Decimal], ...]

    def units_on(self, day: date) -> Decimal:
        """Units of the lot on ``day`` (after that day's splits)."""
        return [u for d, u in self.units if d <= day][-1]


@dataclass(frozen=True)
class WealthItem:
    """One stamp-duty statement period or one holding's IVAFE in a year."""

    year: int
    account: str
    tax: str  # "stamp_duty" or "ivafe"
    holding: Isin | None
    period_end: date
    value: Decimal
    days: int
    rate: Decimal
    amount: Decimal


@dataclass(frozen=True)
class WealthYear:
    """A year's totals; ``ivafe_payable`` is 0 at or below the €12 threshold."""

    year: int
    stamp_duty: Decimal
    ivafe: Decimal
    ivafe_payable: Decimal


@dataclass(frozen=True)
class WealthTaxes:
    """The stamp duty and IVAFE of every computed year, and the years left out."""

    items: tuple[WealthItem, ...]
    years: tuple[WealthYear, ...]
    not_computed: tuple[int, ...] = field(default_factory=tuple)


def parse_custody(value: object) -> dict[str, Custody]:
    """Read ``[parameters.tax.custody]``: account = ``{ where, statements | share }``."""
    if not isinstance(value, dict) or not value:
        raise ValidationError(
            "[parameters.tax] custody must hold one table per account, with where"
        )
    out = {}
    for account, spec in value.items():
        where_ = f"[parameters.tax.custody.{account!r}]"
        if not isinstance(spec, dict):
            raise ValidationError(f"{where_} must be a table")
        options = {w.value for w in Where}
        if spec.get("where") not in options:
            raise ValidationError(f"{where_} where must be one of {sorted(options)}")
        where = Where(spec["where"])
        allowed = {"where", "statements"} if where is Where.ITALY else {"where", "share"}
        unknown = sorted(set(spec) - allowed)
        missing = sorted(allowed - set(spec))
        if unknown or missing:
            raise ValidationError(
                f"{where_} with where = {where.value!r} takes {sorted(allowed)}: "
                f"missing {missing}, refused {unknown}"
            )
        statements = share = None
        if where is Where.ITALY:
            choices = {s.value for s in Statements}
            if spec["statements"] not in choices:
                raise ValidationError(f"{where_} statements must be one of {sorted(choices)}")
            statements = Statements(spec["statements"])
        else:
            raw = spec["share"]
            if type(raw) not in (int, float) or not 0 < raw <= 1:
                raise ValidationError(f"{where_} share must be a number in (0, 1]")
            share = Decimal(repr(raw))
        out[str(account)] = Custody(where, statements, share)
    return out


def round_stamp_duty(amount: Decimal) -> Decimal:
    """Round to €0.10: down for a fraction up to €0.05, up above it (D.P.R. 642/1972, art. 3)."""
    tens = (amount / _TEN_CENTS).to_integral_value(rounding="ROUND_FLOOR") * _TEN_CENTS
    return tens + _TEN_CENTS if amount - tens > _HALF_TEN else tens


def lifo_lots(transactions: Iterable[Transaction]) -> tuple[HeldLot, ...]:
    """Return every lot per account and instrument, sales and transfers out taking the newest."""
    open_lots: dict[tuple[str, Isin], list[dict[str, object]]] = {}
    out: list[HeldLot] = []
    for t in transactions:
        if t.isin is None or t.quantity is None:
            continue
        stack = open_lots.setdefault((t.account, t.isin), [])
        if t.kind in (_K.BUY, _K.TRANSFER_IN):
            stack.append({"acquired": t.trade_date, "units": [(t.trade_date, t.quantity)]})
        elif t.kind is _K.SPLIT:
            for lot in stack:
                units = lot["units"]
                assert isinstance(units, list)
                units.append((t.trade_date, units[-1][1] * t.quantity))
        else:  # a sale or a transfer out
            needed = t.quantity
            while needed > 0:
                if not stack:
                    raise ValidationError(
                        f"{t.account}: {t.isin.code} sold on {t.trade_date} beyond the units held"
                    )
                lot = stack[-1]
                units = lot["units"]
                assert isinstance(units, list)
                held = units[-1][1]
                take = min(held, needed)
                acquired = lot["acquired"]
                assert isinstance(acquired, date)
                # The part taken keeps the lot's history, scaled to the units taken.
                taken = tuple(units) if take == held else _scaled(units, take / held)
                out.append(HeldLot(t.account, t.isin, acquired, t.trade_date, taken))
                needed -= take
                if take == held:
                    stack.pop()
                else:
                    units[:] = _scaled(units, (held - take) / held)
    for (account, isin), stack in open_lots.items():
        for lot in stack:
            units, acquired = lot["units"], lot["acquired"]
            assert isinstance(units, list)
            assert isinstance(acquired, date)
            out.append(HeldLot(account, isin, acquired, None, tuple(units)))
    return tuple(out)


def wealth_taxes(
    *,
    history: LedgerHistory,
    transactions: Sequence[Transaction],
    custody: Mapping[str, Custody],
    prices: Mapping[Isin, PriceSeries],
    to_base: ToBase,
    max_price_age_days: int,
    as_of: date,
) -> WealthTaxes:
    """Compute the stamp duty and IVAFE of every complete calendar year up to ``as_of``."""
    securities = [t for t in transactions if t.isin is not None]
    if not securities:
        return WealthTaxes((), ())
    accounts = sorted({t.account for t in securities})
    missing = [a for a in accounts if a not in custody]
    if missing:
        raise ValidationError(
            f"[parameters.tax] custody does not say where these accounts are held: {missing}"
        )
    opened = {a: min(t.trade_date for t in transactions if t.account == a) for a in accounts}
    first = min(t.trade_date for t in transactions).year
    last = as_of.year if as_of >= date(as_of.year, 12, 31) else as_of.year - 1
    years = [y for y in range(first, last + 1) if FIRST_YEAR <= y <= LAST_YEAR]
    not_computed = tuple(y for y in range(first, last + 1) if y not in years)
    value = _Valuer(prices, to_base, max_price_age_days)
    lots = lifo_lots(transactions)
    items: list[WealthItem] = []
    for year in years:
        for account in accounts:
            spec = custody[account]
            if spec.where is Where.ITALY:
                assert spec.statements is not None
                items += _stamp_duty(
                    history, account, spec.statements, opened[account], year, value
                )
            else:
                assert spec.share is not None
                rate = (
                    IVAFE_PRIVILEGED_RATE
                    if spec.where is Where.ABROAD_PRIVILEGED and year >= _PRIVILEGED_FROM
                    else IVAFE_RATE
                )
                own = [lot for lot in lots if lot.account == account]
                items += _ivafe(own, account, rate, spec.share, year, value)
    totals = []
    for year in years:
        stamp = sum(
            (i.amount for i in items if i.year == year and i.tax == "stamp_duty"), Decimal(0)
        )
        ivafe = sum((i.amount for i in items if i.year == year and i.tax == "ivafe"), Decimal(0))
        payable = ivafe if ivafe > IVAFE_PAYMENT_THRESHOLD else Decimal(0)
        totals.append(WealthYear(year, stamp, ivafe, payable))
    return WealthTaxes(tuple(items), tuple(totals), not_computed)


# --------------------------------------------------------------------------- helpers
def _scaled(units: list[tuple[date, Decimal]], ratio: Decimal) -> tuple[tuple[date, Decimal], ...]:
    return tuple((d, u * ratio) for d, u in units)


class _Valuer:
    """Market values in the base currency from the report's prices."""

    def __init__(self, prices: Mapping[Isin, PriceSeries], to_base: ToBase, max_age: int) -> None:
        self.prices, self.to_base, self.max_age = prices, to_base, max_age

    def __call__(self, isin: Isin, units: Decimal, day: date) -> Decimal:
        if isin not in self.prices:
            raise ValidationError(f"no price series for {isin.code}, needed on {day}")
        series = self.prices[isin]
        try:
            price, _ = series.price_on(day, self.max_age)
        except DataNotFoundError as error:
            raise ValidationError(
                f"{isin.code} on {day}: {error}. On 31 December many exchanges are closed, so "
                "max_price_age_days must reach the last trading day"
            ) from error
        return self.to_base(Money(units * price, series.currency), day).amount


def _period_ends(year: int, statements: Statements) -> list[tuple[date, date]]:
    if statements is Statements.YEAR:
        return [(date(year, 1, 1), date(year, 12, 31))]
    step = 3 if statements is Statements.QUARTER else 1
    out = []
    for month in range(1, 13, step):
        end_month = month + step - 1
        out.append(
            (date(year, month, 1), date(year, end_month, calendar.monthrange(year, end_month)[1]))
        )
    return out


def _stamp_duty(
    history: LedgerHistory,
    account: str,
    statements: Statements,
    opened: date,
    year: int,
    value: _Valuer,
) -> list[WealthItem]:
    items = []
    for start, end in _period_ends(year, statements):
        if opened > end:
            continue
        state = history.state_on(end)
        worth = sum(
            (
                value(isin, position.quantity, end)
                for (acct, isin), position in sorted(
                    state.positions.items(), key=lambda kv: kv[0][1].code
                )
                if acct == account and position.quantity > 0
            ),
            Decimal(0),
        )
        if worth == 0:
            continue
        days = (end - max(start, opened)).days + 1
        whole = statements is Statements.YEAR and opened <= start
        fraction = Decimal(1) if whole else Decimal(days) / Decimal(365)
        amount = max(Decimal(1), round_stamp_duty(STAMP_RATE * worth * fraction))
        items.append(
            WealthItem(year, account, "stamp_duty", None, end, worth, days, STAMP_RATE, amount)
        )
    return items


def _ivafe(
    lots: Sequence[HeldLot],
    account: str,
    rate: Decimal,
    share: Decimal,
    year: int,
    value: _Valuer,
) -> list[WealthItem]:
    start, end = date(year, 1, 1), date(year, 12, 31)
    year_days = Decimal(366 if calendar.isleap(year) else 365)
    per_holding: dict[Isin, list[tuple[Decimal, int]]] = {}
    for lot in lots:
        first = max(lot.acquired, start)
        leaves = lot.disposed if lot.disposed is not None and lot.disposed <= end else None
        stop = leaves if leaves is not None else end + timedelta(days=1)
        days = (stop - first).days
        if days <= 0:
            continue
        on = leaves if leaves is not None else end
        worth = value(lot.isin, lot.units_on(on), on)
        per_holding.setdefault(lot.isin, []).append((worth, days))
    items = []
    for isin in sorted(per_holding, key=lambda i: i.code):
        parts = per_holding[isin]
        raw = sum((rate * w * Decimal(d) / year_days * share for w, d in parts), Decimal(0))
        worth = sum((w for w, _ in parts), Decimal(0))
        weighted = sum((w * d for w, d in parts), Decimal(0))
        days = int((weighted / worth).to_integral_value(ROUND_HALF_UP)) if worth else 0
        amount = raw.quantize(_CENT, rounding=ROUND_HALF_UP)
        items.append(WealthItem(year, account, "ivafe", isin, end, worth, days, rate, amount))
    return items
