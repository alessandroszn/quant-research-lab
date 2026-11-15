"""Swiss tax analytics of a private investor's securities account (phase 9.2).

Analytics, not tax advice and not a ruling. The rules, as checked on 15 November 2026:

- **Gains on private wealth are not taxable** (LIFD/DBG, SR 642.11, art. 16 cpv. 3; the
  cantons the same, LAID art. 7 cpv. 4 lett. b), unless the investor counts as a professional
  securities trader.
- **Professional trading is excluded** when the five criteria of ESTV Circular No. 36 of
  27 July 2012 (section 3) are all met; otherwise it "cannot be excluded" and the tax office
  judges the whole case (section 4). The check here is per calendar year:

  1. the securities sold were held at least 6 months (first in, first out here: the most
     cautious reading of the units sold);
  2. purchases plus sales total no more than 5 times the securities and cash at the start of
     the period (the account's value on the last valuation of the previous year; in the
     first year, its first valuation);
  3. realised gains are below 50 % of the net income you state;
  4. the investments are not debt-financed (as you state; the account never has negative
     cash);
  5. derivatives only hedge own positions (qrlab has no derivative instruments).
- **Income** is taxed at the investor's marginal rate: interest and dividends gross (LIFD
  art. 20 cpv. 1 lett. a and c), and a fund's income, which belongs to its investors (art. 10
  cpv. 2). An accumulating fund's reinvested income is taxed every year, at the fund's yearly
  closing, at the gross amount per unit in the ESTV price list (Circular 25; BGE 151 II 418
  of 9 December 2024). You give those per-unit amounts.
- **Swiss withholding tax** of 35 % on income from Swiss bonds, shares, funds and bank
  balances (LIP/VStG, SR 642.21, art. 4 and 13) is refunded to residents who declare it
  (art. 22 and 23). It is refundable here for instruments domiciled in Switzerland; tax
  withheld on interest without an instrument is listed, not classified.
- **Wealth tax** is cantonal (LAID art. 13 ff.), on the wealth at the end of the year, at the
  rate you state.

Amounts are in CHF (the report's base currency must be CHF). Taxes are estimates rounded to
the cent (half up).
"""

from __future__ import annotations

import calendar
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.transactions import Transaction, TransactionKind
from qrlab.simulation.plan import TaxModel
from qrlab.tax.regime import (
    Cell,
    ColumnKind,
    Paragraph,
    SourcesRef,
    TaxColumn,
    TaxInputs,
    TaxReport,
    TaxTable,
)

__all__ = [
    "RULES_CHECKED_ON",
    "SOURCES",
    "SOURCES_IT",
    "SWITZERLAND",
    "ReportedIncome",
    "SaleHolding",
    "SwissRegime",
    "SwissSettings",
    "add_months",
    "shortest_holdings",
    "swiss_tax_model",
]

RULES_CHECKED_ON = date(2026, 11, 15)
SOURCES = (
    "LIFD/DBG (SR 642.11), art. 10 cpv. 2, 16 cpv. 3, 20 cpv. 1 (version of 2 September 2026)",
    "LAID/StHG (SR 642.14), art. 7 and 13 ff.",
    "ESTV Circular No. 36 of 27 July 2012 (professional securities trading), section 3",
    "ESTV Circular No. 25 (collective investment schemes); BGE 151 II 418 (9 December 2024)",
    "LIP/VStG (SR 642.21), art. 4, 13, 22, 23 (version of 1 January 2025)",
)
SOURCES_IT = (
    "LIFD (RS 642.11), art. 10 cpv. 2, 16 cpv. 3, 20 cpv. 1 (stato al 2 settembre 2026)",
    "LAID (RS 642.14), art. 7 e 13 segg.",
    "Circolare AFC n. 36 del 27 luglio 2012 (commercio professionale di titoli), cifra 3",
    "Circolare AFC n. 25 (investimenti collettivi di capitale); DTF 151 II 418 (9 dicembre 2024)",
    "LIP (RS 642.21), art. 4, 13, 22, 23 (stato al 1° gennaio 2025)",
)
CHF = Currency("CHF")
_HOLDING_MONTHS = 6
_VOLUME_MULTIPLE = Decimal(5)
_GAINS_SHARE = Decimal("0.5")
_CENT = Decimal("0.01")
_K = TransactionKind
_LEFT, _RIGHT = "left", "right"


@dataclass(frozen=True)
class ReportedIncome:
    """A fund's income per unit at a yearly closing, from the ESTV price list."""

    day: date
    per_unit: Decimal
    currency: Currency


@dataclass(frozen=True)
class SwissSettings:
    """The Swiss ``[parameters.tax]`` keys (see :class:`SwissRegime`)."""

    marginal_rate: Decimal
    wealth_tax_rate: Decimal
    net_income: Mapping[int, Decimal]
    debt_financed: bool
    reported_income: Mapping[Isin, tuple[ReportedIncome, ...]]


@dataclass(frozen=True)
class SaleHolding:
    """A sale and the latest acquisition date of the units it sold (first in, first out)."""

    sold: date
    isin: str
    acquired: date

    @property
    def held_six_months(self) -> bool:
        """Whether every unit sold was held at least 6 calendar months."""
        return self.sold >= add_months(self.acquired, _HOLDING_MONTHS)


@dataclass
class _Lot:
    day: date
    units: Decimal


def add_months(day: date, months: int) -> date:
    """Return ``day`` plus calendar ``months`` (the 31st becomes the month's last day)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def shortest_holdings(transactions: Iterable[Transaction]) -> tuple[SaleHolding, ...]:
    """Return every sale with the latest acquisition date of the units it sold.

    Units are taken first in, first out per account and instrument: purchases and transfers
    in add lots, sales and transfers out remove the oldest first, and a split scales them.
    """
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
            needed, latest = t.quantity, date.min
            while needed > 0 and queue:
                lot = queue[0]
                take = min(lot.units, needed)
                latest = max(latest, lot.day)
                lot.units -= take
                needed -= take
                if lot.units == 0:
                    queue.popleft()
            if t.kind is _K.SELL:
                out.append(SaleHolding(t.trade_date, t.isin.code, latest))
    return tuple(out)


class SwissRegime:
    """Switzerland, for a private investor's securities account."""

    country = "ch"
    keys = frozenset(
        {"marginal_rate", "wealth_tax_rate", "net_income", "debt_financed", "reported_income"}
    )
    optional_keys: frozenset[str] = frozenset()
    base_currency: Currency | None = CHF

    def parse(self, table: Mapping[str, object]) -> SwissSettings:
        """Read the rates, the net income by year, debt financing and the price-list income."""
        net_income = table["net_income"]
        if not isinstance(net_income, dict):
            raise ValidationError("net_income must be a table of year = amount (may be empty)")
        incomes = {}
        for year, amount in net_income.items():
            if not str(year).isdigit():
                raise ValidationError(f"net_income: {year!r} is not a year")
            if type(amount) not in (int, float) or amount < 0:
                raise ValidationError(f"net_income of {year} must be a number >= 0")
            incomes[int(year)] = Decimal(repr(amount))
        if type(table["debt_financed"]) is not bool:
            raise ValidationError("debt_financed must be true or false")
        reported = table["reported_income"]
        if not isinstance(reported, dict):
            raise ValidationError("reported_income must be a table of ISIN = [ ... ]")
        return SwissSettings(
            marginal_rate=_rate(table, "marginal_rate"),
            wealth_tax_rate=_rate(table, "wealth_tax_rate"),
            net_income=incomes,
            debt_financed=bool(table["debt_financed"]),
            reported_income={
                Isin(code): _reported(code, items) for code, items in reported.items()
            },
        )

    def report(self, inputs: TaxInputs, settings: object) -> TaxReport:
        """Return the gains check, the income, the withholding tax and the wealth by year."""
        if not isinstance(settings, SwissSettings):
            raise ValidationError(f"Swiss settings expected, got {settings!r}")
        if inputs.history.base != CHF:
            raise ValidationError(
                f'Swiss tax analytics need base_currency = "CHF", not {inputs.history.base}'
            )
        return _Report(inputs, settings).build()


SWITZERLAND = SwissRegime()
"""Switzerland's :class:`~qrlab.tax.regime.TaxRegime`."""


def swiss_tax_model(
    *, wealth_tax_rate: float, income_tax_rate: float, taxable_yield: float
) -> TaxModel:
    """Return a private investor's taxes for projections: no gains tax, wealth and income.

    Every rate is yours to state: the cantonal wealth-tax rate, your marginal income rate and
    the taxable yield of the holdings (for an accumulating fund, its reported income per
    unit over its price).
    """
    return TaxModel(
        0.0, wealth_tax_rate, income_tax_rate=income_tax_rate, taxable_yield=taxable_yield
    )


# --------------------------------------------------------------------------- the report
_YEAR_COLUMNS = (
    TaxColumn("year", "tax_year", ColumnKind.YEAR, _LEFT),
    TaxColumn("gains", "ch_gains", ColumnKind.MONEY, _RIGHT),
    TaxColumn("income", "ch_income", ColumnKind.MONEY, _RIGHT),
    TaxColumn("income_tax", "ch_income_tax", ColumnKind.MONEY, _RIGHT),
    TaxColumn("withholding_refundable", "ch_refundable", ColumnKind.MONEY, _RIGHT),
    TaxColumn("wealth", "ch_wealth", ColumnKind.MONEY, _RIGHT, none_label="ch_year_open"),
    TaxColumn("wealth_tax", "ch_wealth_tax", ColumnKind.MONEY, _RIGHT, none_label="ch_year_open"),
    TaxColumn("safe_haven", "ch_safe_haven", ColumnKind.LABEL, _LEFT, prefix="ch_conclusion_"),
)
_CRITERIA_COLUMNS = (
    TaxColumn("year", "tax_year", ColumnKind.YEAR, _LEFT),
    TaxColumn("criterion", "ch_criterion", ColumnKind.LABEL, _LEFT, prefix="ch_criterion_"),
    TaxColumn("value", "value", ColumnKind.MONEY, _RIGHT, none_label=""),
    TaxColumn("limit", "ch_limit", ColumnKind.MONEY, _RIGHT, none_label=""),
    TaxColumn("detail", "ch_detail", ColumnKind.TEXT, _LEFT),
    TaxColumn("result", "ch_result", ColumnKind.LABEL, _LEFT, prefix="ch_result_"),
)
_INCOME_COLUMNS = (
    TaxColumn("date", "date", ColumnKind.DATE, _LEFT),
    TaxColumn("isin", "holding", ColumnKind.HOLDING, _LEFT, none_label="ch_cash"),
    TaxColumn("kind", "ch_income_kind", ColumnKind.LABEL, _LEFT, prefix="ch_income_"),
    TaxColumn("units", "ch_units", ColumnKind.NUMBER, _RIGHT, none_label=""),
    TaxColumn("per_unit", "ch_per_unit", ColumnKind.NUMBER, _RIGHT, none_label=""),
    TaxColumn("currency", "currency", ColumnKind.TEXT, _LEFT),
    TaxColumn("gross", "ch_gross", ColumnKind.MONEY, _RIGHT),
    TaxColumn("withheld", "tax_withheld", ColumnKind.MONEY, _RIGHT),
    TaxColumn("refundable", "ch_refundable", ColumnKind.MONEY, _RIGHT),
)
_SETTING_COLUMNS = (
    TaxColumn("item", "", ColumnKind.LABEL, _LEFT),
    TaxColumn("value", "value", ColumnKind.SHARE, _RIGHT),
)
Row = tuple[Cell, ...]


@dataclass(frozen=True)
class _Item:
    """An income item of the year: a dividend, an interest or a fund's reported income."""

    day: date
    isin: str | None
    kind: str
    units: Decimal | None
    per_unit: Decimal | None
    currency: str
    gross: Decimal
    withheld: Decimal
    refundable: Decimal

    def row(self) -> Row:
        return (
            self.day, self.isin, self.kind, self.units, self.per_unit, self.currency,
            self.gross, self.withheld, self.refundable,
        )  # fmt: skip


@dataclass(frozen=True)
class _Check:
    """One Circular 36 criterion in one year."""

    year: int
    criterion: str
    value: Decimal | None
    limit: Decimal | None
    detail: str
    result: str

    def row(self) -> Row:
        return (self.year, self.criterion, self.value, self.limit, self.detail, self.result)


@dataclass(frozen=True)
class _Year:
    year: int
    gains: Decimal
    income: Decimal
    income_tax: Decimal
    refundable: Decimal
    wealth: Decimal | None
    wealth_tax: Decimal | None
    conclusion: str

    def row(self) -> Row:
        return (
            self.year, self.gains, self.income, self.income_tax, self.refundable, self.wealth,
            self.wealth_tax, self.conclusion,
        )  # fmt: skip


class _Report:
    def __init__(self, inputs: TaxInputs, settings: SwissSettings) -> None:
        self.inputs = inputs
        self.settings = settings
        days = [t.trade_date for t in inputs.transactions]
        self.first = min(days).year if days else inputs.as_of.year
        self.years = range(self.first, inputs.as_of.year + 1)
        self.holdings = shortest_holdings(inputs.transactions)
        self.started_from_first_valuation = False

    def build(self) -> TaxReport:
        items = self._income_items()
        rows: list[_Year] = []
        criteria: list[_Check] = []
        for year in self.years:
            year_items = [i for i in items if i.day.year == year]
            income = sum((i.gross for i in year_items), Decimal(0))
            wealth = self._wealth(year)
            checks = self._criteria(year)
            criteria += checks
            rows.append(
                _Year(
                    year=year,
                    gains=self._gains(year),
                    income=income,
                    income_tax=_cents(self.settings.marginal_rate * income),
                    refundable=sum((i.refundable for i in year_items), Decimal(0)),
                    wealth=wealth,
                    wealth_tax=None
                    if wealth is None
                    else _cents(self.settings.wealth_tax_rate * wealth),
                    conclusion=_conclusion([c.result for c in checks]),
                )
            )
        paragraphs = [
            Paragraph("ch_intro", (("checked", RULES_CHECKED_ON),)),
            Paragraph("ch_gains_rule"),
            Paragraph("ch_safe_haven_rule"),
        ]
        if self.started_from_first_valuation:
            paragraphs.append(Paragraph("ch_first_year", (("year", str(self.first)),)))
        paragraphs += [
            Paragraph("ch_income_rule"),
            Paragraph("ch_withholding_rule"),
            Paragraph("ch_wealth_rule"),
            Paragraph("tax_sources", (("sources", SourcesRef()),)),
        ]
        settings = TaxTable(
            "ch_settings",
            _SETTING_COLUMNS,
            (
                ("ch_marginal_rate", self.settings.marginal_rate),
                ("ch_wealth_tax_rate", self.settings.wealth_tax_rate),
            ),
        )
        return TaxReport(
            country="ch",
            as_of=self.inputs.as_of,
            checked_on=RULES_CHECKED_ON,
            sources={"en": SOURCES, "it": SOURCES_IT},
            paragraphs=tuple(paragraphs),
            tables=(
                settings,
                TaxTable(
                    "ch_years",
                    _YEAR_COLUMNS,
                    tuple(r.row() for r in rows),
                    file="ch_years",
                    index="year",
                ),
                TaxTable(
                    "ch_safe_haven",
                    _CRITERIA_COLUMNS,
                    tuple(c.row() for c in criteria),
                    file="ch_safe_haven",
                    index="year",
                    note="ch_safe_haven_note",
                ),
                TaxTable(
                    "ch_income_items",
                    _INCOME_COLUMNS,
                    tuple(i.row() for i in items),
                    file="ch_income",
                    index="date",
                    note="ch_income_note",
                ),
            ),
            scalars=self._scalars(rows),
        )

    # ------------------------------------------------------------------ income
    def _income_items(self) -> list[_Item]:
        inputs = self.inputs
        items: list[_Item] = []
        for income in inputs.history.income:
            if income.trade_date > inputs.as_of:
                continue
            instrument = None if income.isin is None else inputs.instruments.get(income.isin)
            swiss = instrument is not None and instrument.domicile == "CH"
            items.append(
                _Item(
                    day=income.trade_date,
                    isin=None if income.isin is None else income.isin.code,
                    kind="dividend" if income.kind is _K.DIVIDEND else "interest",
                    units=None,
                    per_unit=None,
                    currency="",
                    gross=income.gross_base,
                    withheld=income.taxes_base,
                    refundable=income.taxes_base if swiss else Decimal(0),
                )
            )
        for isin, entries in self.settings.reported_income.items():
            for entry in entries:
                if entry.day > inputs.as_of:
                    continue
                units = sum(
                    (
                        p.quantity
                        for (_, code), p in inputs.history.state_on(entry.day).positions.items()
                        if code == isin
                    ),
                    Decimal(0),
                )
                if units == 0:
                    raise ValidationError(
                        f"reported_income: no units of {isin.code} are held on {entry.day}"
                    )
                amount = inputs.to_base(
                    Money(units * entry.per_unit, entry.currency), entry.day
                ).amount
                items.append(
                    _Item(
                        day=entry.day,
                        isin=isin.code,
                        kind="reported_income",
                        units=units,
                        per_unit=entry.per_unit,
                        currency=entry.currency.code,
                        gross=amount,
                        withheld=Decimal(0),
                        refundable=Decimal(0),
                    )
                )
        items.sort(key=lambda item: item.day)
        return items

    # ------------------------------------------------------------------ per year
    def _gains(self, year: int) -> Decimal:
        return sum(
            (g.gain_base for g in self.inputs.history.realised if g.trade_date.year == year),
            Decimal(0),
        )

    def _value_on_or_before(self, day: date) -> Decimal | None:
        valuation = self.inputs.valuation
        known = [d for d in valuation.totals if d <= day]
        return valuation.totals[max(known)] if known else None

    def _wealth(self, year: int) -> Decimal | None:
        end = date(year, 12, 31)
        return None if end > self.inputs.as_of else self._value_on_or_before(end)

    def _start_value(self, year: int) -> Decimal | None:
        value = self._value_on_or_before(date(year - 1, 12, 31))
        if value is not None:
            return value
        in_year = [d for d in self.inputs.valuation.totals if d.year == year]
        if not in_year:
            return None
        self.started_from_first_valuation = True
        return self.inputs.valuation.totals[min(in_year)]

    def _criteria(self, year: int) -> list[_Check]:
        rows: list[_Check] = []
        sales = [h for h in self.holdings if h.sold.year == year]
        if sales:
            shortest = min(sales, key=lambda h: (h.sold - h.acquired, h.sold))
            detail = f"{shortest.acquired.isoformat()} → {shortest.sold.isoformat()}"
            held = "met" if all(h.held_six_months for h in sales) else "not_met"
        else:
            detail, held = "", "met"
        rows.append(_Check(year, "holding", None, None, detail, held))

        volume = self._volume(year)
        start = self._start_value(year)
        limit = None if start is None else _VOLUME_MULTIPLE * start
        result = "not_checked" if limit is None else "met" if volume <= limit else "not_met"
        rows.append(_Check(year, "volume", volume, limit, "", result))

        gains = self._gains(year)
        income = self.settings.net_income.get(year)
        gains_limit = None if income is None else _GAINS_SHARE * income
        result = (
            "not_checked" if gains_limit is None else "met" if gains < gains_limit else "not_met"
        )
        rows.append(_Check(year, "gains", gains, gains_limit, "", result))
        debt = "not_checked" if self.settings.debt_financed else "met"
        rows.append(_Check(year, "debt", None, None, "", debt))
        rows.append(_Check(year, "derivatives", None, None, "", "met"))
        return rows

    def _volume(self, year: int) -> Decimal:
        total = Decimal(0)
        for t in self.inputs.transactions:
            if t.trade_date.year != year or t.kind not in (_K.BUY, _K.SELL):
                continue
            assert t.quantity is not None  # a trade has a quantity and a price
            assert t.price is not None
            gross = Money(t.quantity * t.price.amount, t.price.currency)
            total += self.inputs.to_base(gross, t.trade_date).amount
        return total

    def _scalars(self, rows: Sequence[_Year]) -> dict[str, Decimal]:
        """Return the latest complete calendar year's numbers (the current one if none)."""
        as_of = self.inputs.as_of
        latest = as_of.year if date(as_of.year, 12, 31) <= as_of else as_of.year - 1
        row = next((r for r in rows if r.year == latest), rows[-1])
        scalars = {
            "gains_realised": row.gains,
            "safe_haven_met": Decimal(1 if row.conclusion == "met" else 0),
            "income_taxable": row.income,
            "income_tax_estimate": row.income_tax,
            "withholding_refundable": row.refundable,
        }
        if row.wealth is not None and row.wealth_tax is not None:
            scalars |= {"wealth": row.wealth, "wealth_tax_estimate": row.wealth_tax}
        return scalars


# --------------------------------------------------------------------------- helpers
def _conclusion(results: Sequence[str]) -> str:
    if "not_met" in results:
        return "not_excluded"
    return "incomplete" if "not_checked" in results else "met"


def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def _rate(table: Mapping[str, object], key: str) -> Decimal:
    value = table[key]
    if type(value) not in (int, float) or not 0 <= value < 1:  # type: ignore[operator]
        raise ValidationError(f"{key} must be a number in [0, 1), got {value!r}")
    return Decimal(repr(value))


def _reported(code: str, items: object) -> tuple[ReportedIncome, ...]:
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise ValidationError(
            f"reported_income of {code} must be a list of {{ date, per_unit, currency }}"
        )
    out = []
    for item in items:
        if set(item) != {"date", "per_unit", "currency"}:
            raise ValidationError(
                f"reported_income of {code} needs date, per_unit and currency, got {sorted(item)}"
            )
        day = item["date"]
        if isinstance(day, datetime) or not isinstance(day, date):
            raise ValidationError(f"reported_income of {code}: date must be a TOML date")
        per_unit = item["per_unit"]
        if not isinstance(per_unit, str):
            raise ValidationError(
                f'reported_income of {code}: per_unit must be a quoted decimal such as "2.50"'
            )
        try:
            amount = Decimal(per_unit)
        except InvalidOperation:
            raise ValidationError(
                f"reported_income of {code}: per_unit {per_unit!r} is not a decimal"
            ) from None
        if not amount.is_finite() or amount < 0:
            raise ValidationError(f"reported_income of {code}: per_unit must be >= 0")
        out.append(ReportedIncome(day, amount, Currency(item["currency"])))
    return tuple(sorted(out, key=lambda r: r.day))
