"""The Italian tax position of an individual's securities account: analytics, not tax advice.

The rules, as checked on 14 November 2026 (design note 8.6):

- **Capital income versus other income.** A gain on selling units of an investment fund or
  ETF (OICR) is *reddito di capitale* (TUIR, D.P.R. 917/1986, art. 44; from 1 January 2027 the
  testo unico D.Lgs. 117/2026, art. 46): it is taxed in full and absorbs no losses. A loss on
  those units, and gains and losses on shares, bonds and ETCs, are *redditi diversi* (TUIR
  art. 67; D.Lgs. 117/2026 art. 76).
- **Losses** offset only *redditi diversi* gains and are carried forward to the fourth tax
  year after the one in which they were realised (TUIR art. 68, comma 5; D.Lgs. 117/2026
  art. 77). They are used oldest first here, and the remainder expires on 31 December of
  year + 4.
- **Rates.** 26 % (D.L. 66/2014, art. 3). The part of a gain or loss due to Italian and
  white-list government bonds counts for 48.08 % of its amount, i.e. it is reduced by 51.92 %
  (D.L. 138/2011, art. 2; D.M. 13 December 2011; Circolare Agenzia delle Entrate 19/E of 27
  June 2014, which works the fund example 300 x 26.5 % -> base 258.72, tax 67.27). For a fund
  the share is the average share of public bonds it publishes; for a bond it is 1 or 0.
- **Regimes.** *Amministrato* (D.Lgs. 461/1997, art. 6): the intermediary taxes each sale when
  it happens and keeps the account's losses balance; a later loss does not give back tax
  already withheld. *Dichiarativo*: gains and losses of a year are netted in the tax return,
  then earlier losses are used.
- **Not in force.** L. 111/2023, art. 5, plans one category of financial income; no
  implementing decree has done so (D.Lgs. 148/2026 does not). The rules below are applied to
  sales from 1 July 2014 (the 26 % rate) to 31 December 2027 only; anything else raises.
- **Non-harmonised funds** (a fund domiciled outside the EU and EEA, e.g. a US ETF) are taxed
  at progressive IRPEF rates: they are flagged and nothing is computed for them.

Taxes are rounded to the cent per sale (half up); bases keep exact decimals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from qrlab.core.errors import ValidationError
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import Instrument, InstrumentType
from qrlab.portfolio.ledger import LedgerHistory, RealisedGain, ToBase
from qrlab.portfolio.transactions import Transaction, TransactionKind

__all__ = [
    "PUBLIC_BOND_REDUCTION",
    "RATE",
    "RULES_CHECKED_ON",
    "SOURCES",
    "Category",
    "LossLot",
    "Regime",
    "TaxEvent",
    "TaxPosition",
    "italian_tax_position",
]

RATE = Decimal("0.26")
PUBLIC_BOND_REDUCTION = Decimal("0.5192")  # the public-bond share counts for 48.08 %
RULES_CHECKED_ON = date(2026, 11, 14)
_FIRST_SALE, _LAST_SALE = date(2014, 7, 1), date(2027, 12, 31)
_CENT = Decimal("0.01")
_FUNDS = {InstrumentType.ETF, InstrumentType.FUND}
_EU_EEA = frozenset(
    {
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE",
        "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK", "IS", "LI", "NO",
    }
)  # fmt: skip
SOURCES = (
    "TUIR, D.P.R. 917/1986, artt. 44, 67, 68 (to 31/12/2026)",
    "Testo unico imposte sui redditi, D.Lgs. 117/2026, artt. 46, 76, 77 (from 1/1/2027)",
    "D.L. 66/2014, art. 3 (26 %)",
    "D.L. 138/2011, art. 2; D.M. 13/12/2011; Circolare AdE 19/E del 27/06/2014 (48.08 %)",
    "D.Lgs. 461/1997, art. 6 (regime amministrato)",
    "L. 111/2023, art. 5: unification of financial income not in force (checked 14/11/2026)",
)


class Regime(Enum):
    """How the account is taxed."""

    AMMINISTRATO = "amministrato"
    DICHIARATIVO = "dichiarativo"


class Category(Enum):
    """Tax category of a realised result."""

    CAPITAL_INCOME = "redditi_di_capitale"
    OTHER_INCOME = "redditi_diversi"
    NOT_COMPUTED = "not_computed"  # a non-harmonised fund: progressive IRPEF rates


@dataclass(frozen=True)
class TaxEvent:
    """One sale and its tax, in the base currency.

    ``gain`` is the result net of fees and before any tax; ``base`` the amount that counts
    after the public-bond reduction (a positive number for a gain, the deductible amount for
    a loss); ``offset`` the losses used against it; ``tax_due`` is ``None`` when not computed.
    """

    trade_date: date
    account: str
    isin: str
    category: Category
    gain: Decimal
    public_share: Decimal
    base: Decimal
    offset: Decimal
    tax_due: Decimal | None
    tax_withheld: Decimal

    @property
    def difference(self) -> Decimal:
        """Tax withheld minus tax due (0 when nothing is computed)."""
        return Decimal(0) if self.tax_due is None else self.tax_withheld - self.tax_due


@dataclass(frozen=True)
class LossLot:
    """Losses realised in one year: how much was used, expired and is left."""

    year: int
    amount: Decimal
    used: Decimal
    expired: Decimal

    @property
    def remaining(self) -> Decimal:
        """Amount still usable."""
        return self.amount - self.used - self.expired

    @property
    def expires(self) -> date:
        """Last day the losses can be used: 31 December of the fourth following year."""
        return date(self.year + 4, 12, 31)


@dataclass(frozen=True)
class TaxPosition:
    """The account's tax events, losses balance and totals on ``as_of``."""

    as_of: date
    regime: Regime
    events: tuple[TaxEvent, ...]
    losses: tuple[LossLot, ...]
    flagged: tuple[str, ...]
    sources: tuple[str, ...] = SOURCES

    @property
    def tax_due(self) -> Decimal:
        """Total tax due on the computed events."""
        return sum((e.tax_due for e in self.events if e.tax_due is not None), Decimal(0))

    @property
    def tax_withheld(self) -> Decimal:
        """Total tax the export records on the sales."""
        return sum((e.tax_withheld for e in self.events), Decimal(0))

    @property
    def losses_remaining(self) -> Decimal:
        """Losses still usable on ``as_of``."""
        return sum((lot.remaining for lot in self.losses), Decimal(0))


class _Balance:
    """Loss lots by year, used oldest first, expiring after year + 4."""

    def __init__(self) -> None:
        self.lots: dict[int, list[Decimal]] = {}  # year -> [amount, used, expired]

    def add(self, year: int, amount: Decimal) -> None:
        self.lots.setdefault(year, [Decimal(0), Decimal(0), Decimal(0)])[0] += amount

    def expire(self, before_year: int) -> None:
        """Expire lots that cannot be used in ``before_year`` (realised before year - 4)."""
        for year, lot in self.lots.items():
            if year + 4 < before_year:
                lot[2] = lot[0] - lot[1]

    def use(self, amount: Decimal, year: int) -> Decimal:
        """Use up to ``amount`` of usable losses in ``year``; return the amount used."""
        self.expire(year)
        used = Decimal(0)
        for lot_year in sorted(self.lots):
            lot = self.lots[lot_year]
            free = lot[0] - lot[1] - lot[2]
            if lot_year > year or free <= 0 or used >= amount:
                continue
            take = min(free, amount - used)
            lot[1] += take
            used += take
        return used

    def result(self, as_of: date) -> tuple[LossLot, ...]:
        self.expire(as_of.year)
        return tuple(LossLot(y, *self.lots[y]) for y in sorted(self.lots))


def italian_tax_position(
    history: LedgerHistory,
    transactions: Sequence[Transaction],
    instruments: Mapping[Isin, Instrument],
    *,
    regime: Regime,
    public_share: Mapping[Isin, Decimal],
    as_of: date,
    to_base: ToBase,
) -> TaxPosition:
    """Return the tax events of every sale, the losses balance and the totals.

    Parameters
    ----------
    history, transactions
        The replayed ledger and the transactions it was replayed from (the sales' fees and
        withheld taxes are read from them).
    instruments
        Master data of every instrument sold: its type and domicile decide the category.
    regime
        How the account is taxed.
    public_share
        Share of Italian and white-list government bonds, in [0, 1], for every fund and bond
        sold (an equity fund declares 0). Nothing is assumed.
    as_of
        Date of the losses balance.
    to_base
        The converter the ledger used, for the withheld taxes.
    """
    if not isinstance(regime, Regime):
        raise ValidationError(f"regime must be a Regime, got {regime!r}")
    sales: dict[tuple[object, ...], list[Transaction]] = {}
    for t in transactions:
        if t.kind is TransactionKind.SELL:
            sales.setdefault((t.trade_date, t.account, t.isin, t.quantity), []).append(t)
    events: list[TaxEvent] = []
    flagged: list[str] = []
    balance = _Balance()
    pending: dict[int, list[TaxEvent]] = {}  # dichiarativo: the year's events, netted later
    for gain in sorted(history.realised, key=lambda g: g.trade_date):
        sale = _sale_of(gain, sales)
        withheld = to_base(sale.taxes, sale.trade_date).amount if sale.taxes.amount else Decimal(0)
        event = _classify(gain, withheld, instruments, public_share)
        if event.category is Category.NOT_COMPUTED:
            flagged.append(event.isin)
            events.append(event)
            continue
        if regime is Regime.DICHIARATIVO:
            pending.setdefault(gain.trade_date.year, []).append(event)
            continue
        events.append(_settle(event, balance))
    for year in sorted(pending):
        events += _settle_year(pending[year], balance, year)
    events.sort(key=lambda e: e.trade_date)
    return TaxPosition(
        as_of=as_of,
        regime=regime,
        events=tuple(events),
        losses=balance.result(as_of),
        flagged=tuple(sorted(set(flagged))),
    )


def _sale_of(gain: RealisedGain, sales: dict[tuple[object, ...], list[Transaction]]) -> Transaction:
    """Return (and consume) the sale transaction a realised gain comes from."""
    key = (gain.trade_date, gain.account, gain.isin, gain.quantity)
    if not sales.get(key):  # pragma: no cover - every realised gain comes from a sale
        raise ValidationError(f"no sale of {gain.isin.code} on {gain.trade_date}")
    return sales[key].pop(0)


def _classify(
    gain: RealisedGain,
    withheld: Decimal,
    instruments: Mapping[Isin, Instrument],
    public_share: Mapping[Isin, Decimal],
) -> TaxEvent:
    """Return the event of one sale with its category and base, before any offset."""
    if not _FIRST_SALE <= gain.trade_date <= _LAST_SALE:
        raise ValidationError(
            f"sale of {gain.isin.code} on {gain.trade_date}: the rules here cover sales from "
            f"{_FIRST_SALE} to {_LAST_SALE} (checked on {RULES_CHECKED_ON})"
        )
    instrument = instruments.get(gain.isin)
    if instrument is None:
        raise ValidationError(f"{gain.isin.code} is sold but missing from the instruments file")
    result = gain.gain_base + withheld  # net of fees, before tax
    fund = instrument.instrument_type in _FUNDS
    if fund and instrument.domicile not in _EU_EEA:
        return TaxEvent(
            gain.trade_date, gain.account, gain.isin.code, Category.NOT_COMPUTED, result,
            Decimal(0), Decimal(0), Decimal(0), None, withheld,
        )  # fmt: skip
    share = Decimal(0)
    if fund or instrument.instrument_type is InstrumentType.BOND:
        if gain.isin not in public_share:
            raise ValidationError(
                f"{gain.isin.code}: give its public-bond share in [parameters.tax.public_share] "
                "(0 for an equity fund, 1 for a government bond)"
            )
        share = Decimal(public_share[gain.isin])
        if not Decimal(0) <= share <= Decimal(1):
            raise ValidationError(f"{gain.isin.code}: public-bond share must be in [0, 1]")
    base = abs(result) * (Decimal(1) - share * PUBLIC_BOND_REDUCTION)
    category = Category.CAPITAL_INCOME if fund and result > 0 else Category.OTHER_INCOME
    return TaxEvent(
        gain.trade_date, gain.account, gain.isin.code, category, result, share, base,
        Decimal(0), None, withheld,
    )  # fmt: skip


def _tax(amount: Decimal) -> Decimal:
    return (amount * RATE).quantize(_CENT, rounding=ROUND_HALF_UP)


def _settle(event: TaxEvent, balance: _Balance) -> TaxEvent:
    """Amministrato: tax one sale when it happens, using or adding losses."""
    year = event.trade_date.year
    if event.gain <= 0:
        balance.add(year, event.base)
        return _with(event, Decimal(0), Decimal(0))
    if event.category is Category.CAPITAL_INCOME:
        return _with(event, Decimal(0), _tax(event.base))
    offset = balance.use(event.base, year)
    return _with(event, offset, _tax(event.base - offset))


def _settle_year(events: list[TaxEvent], balance: _Balance, year: int) -> list[TaxEvent]:
    """Dichiarativo: net the year's other-income results, then use earlier losses.

    Capital income is taxed in full. The year's other-income gains and losses are netted; a
    net loss joins the losses balance, a net gain is reduced by earlier losses, oldest first.
    The year's tax is spread over its gains in proportion to their bases, to the cent, with
    the rounding remainder on the last gain, so that the events add up to the year's tax.
    """
    out = [
        _with(e, Decimal(0), _tax(e.base)) for e in events if e.category is Category.CAPITAL_INCOME
    ]
    others = [e for e in events if e.category is Category.OTHER_INCOME]
    gains = [e for e in others if e.gain > 0]
    gross = sum((e.base for e in gains), Decimal(0))
    net = gross - sum((e.base for e in others if e.gain <= 0), Decimal(0))
    out += [_with(e, Decimal(0), Decimal(0)) for e in others if e.gain <= 0]
    if net <= 0:
        if net < 0:
            balance.add(year, -net)
        out += [_with(e, e.base, Decimal(0)) for e in gains]
        return out
    taxable = net - balance.use(net, year)
    total = _tax(taxable)
    spent = Decimal(0)
    for k, e in enumerate(gains):
        weight = e.base / gross
        tax = total - spent if k == len(gains) - 1 else (total * weight).quantize(_CENT)
        spent += tax
        out.append(_with(e, e.base - taxable * weight, tax))
    return out


def _with(event: TaxEvent, offset: Decimal, tax: Decimal) -> TaxEvent:
    return TaxEvent(
        event.trade_date, event.account, event.isin, event.category, event.gain,
        event.public_share, event.base, offset, tax, event.tax_withheld,
    )  # fmt: skip
