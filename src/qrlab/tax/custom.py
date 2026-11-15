"""A configurable tax model for countries not modelled in detail (phase 9.3).

**A simplified model you configure, not a country's law.** You state the rules, and they are
applied per calendar year, in this order:

1. each sale's result is the ledger's realised gain or loss, at average cost;
2. the share of the units sold that were held at least ``exempt_after_months`` (matched
   first in, first out: an approximation next to the average cost) is exempt;
3. losses: ``"ignored"``, so each taxable gain is taxed alone; or ``"netted"``, so the year's
   taxable gains and losses are netted, a net loss joins a balance usable for
   ``loss_carry_years`` following years (oldest first), and a net gain is reduced by that
   balance;
4. ``gains_allowance`` is taken off what is left, never below 0;
5. gains tax = ``gains_rate`` x the rest; income tax = ``income_rate`` x the gross dividends and
   interest; wealth tax = ``wealth_tax_rate`` x the value at the last valuation of each year
   that has ended. Tax withheld on income is shown, not credited.

Taxes are rounded to the cent (half up). Amounts are in the report's base currency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.portfolio.ledger import RealisedGain
from qrlab.simulation.losses import LossRules
from qrlab.simulation.plan import TaxModel
from qrlab.tax.lots import FifoSale, fifo_sales
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

__all__ = ["CUSTOM", "NOTICE", "CustomRegime", "CustomSettings", "custom_tax_model"]

NOTICE = "The tax figures come from a simplified model you configured, not from a country's law."
_CENT = Decimal("0.01")
_LEFT, _RIGHT = "left", "right"
_LOSSES = ("ignored", "netted")
_SOURCES = {
    "en": ("the settings you stated in [parameters.tax]; no country's law is applied",),
    "it": ("le impostazioni che hai indicato in [parameters.tax]; non si applica la legge di "
           "alcun paese",),
}  # fmt: skip


@dataclass(frozen=True)
class CustomSettings:
    """The configurable model's ``[parameters.tax]`` keys (see :class:`CustomRegime`)."""

    description: str
    gains_rate: Decimal
    income_rate: Decimal
    losses: str
    loss_carry_years: int
    exempt_after_months: int
    gains_allowance: Decimal
    wealth_tax_rate: Decimal


class CustomRegime:
    """The configurable model: every rule stated by you (``country = "custom"``)."""

    country = "custom"
    keys = frozenset(
        {
            "description", "gains_rate", "income_rate", "losses", "loss_carry_years",
            "exempt_after_months", "gains_allowance", "wealth_tax_rate",
        }
    )  # fmt: skip
    optional_keys: frozenset[str] = frozenset()
    base_currency: Currency | None = None

    def parse(self, table: Mapping[str, object]) -> CustomSettings:
        """Read and check the stated rules."""
        description = table["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValidationError("description must be non-empty text")
        losses = table["losses"]
        if losses not in _LOSSES:
            raise ValidationError(f"losses must be one of {list(_LOSSES)}, got {losses!r}")
        carry = _whole(table, "loss_carry_years")
        if losses == "ignored" and carry != 0:
            raise ValidationError("loss_carry_years must be 0 when losses are ignored")
        allowance = table["gains_allowance"]
        if type(allowance) not in (int, float) or allowance < 0:  # type: ignore[operator]
            raise ValidationError(f"gains_allowance must be a number >= 0, got {allowance!r}")
        return CustomSettings(
            description=description.strip(),
            gains_rate=_rate(table, "gains_rate"),
            income_rate=_rate(table, "income_rate"),
            losses=str(losses),
            loss_carry_years=carry,
            exempt_after_months=_whole(table, "exempt_after_months"),
            gains_allowance=Decimal(repr(allowance)),
            wealth_tax_rate=_rate(table, "wealth_tax_rate"),
        )

    def report(self, inputs: TaxInputs, settings: object) -> TaxReport:
        """Return the gains, income and wealth taxes by year under the stated rules."""
        if not isinstance(settings, CustomSettings):
            raise ValidationError(f"custom settings expected, got {settings!r}")
        return _Report(inputs, settings).build()


CUSTOM = CustomRegime()
"""The configurable model's :class:`~qrlab.tax.regime.TaxRegime`."""


def custom_tax_model(settings: CustomSettings, *, taxable_yield: float) -> TaxModel:
    """Return the model's taxes for projections.

    The gains and wealth-tax rates; netted losses carried as stated (every asset's losses
    count: no fund rule); the income rate on ``taxable_yield``. The exemption by holding
    period and the allowance are not modelled in projections.
    """
    losses = (
        LossRules(settings.loss_carry_years, frozenset()) if settings.losses == "netted" else None
    )
    return TaxModel(
        float(settings.gains_rate),
        float(settings.wealth_tax_rate),
        losses=losses,
        income_tax_rate=float(settings.income_rate),
        taxable_yield=taxable_yield,
    )


# --------------------------------------------------------------------------- the report
Row = tuple[Cell, ...]
_YEAR_COLUMNS = (
    TaxColumn("year", "tax_year", ColumnKind.YEAR, _LEFT),
    TaxColumn("result", "custom_result", ColumnKind.MONEY, _RIGHT),
    TaxColumn("exempt", "custom_exempt_amount", ColumnKind.MONEY, _RIGHT),
    TaxColumn("taxable_gains", "custom_taxable_gains", ColumnKind.MONEY, _RIGHT),
    TaxColumn("taxable_losses", "custom_taxable_losses", ColumnKind.MONEY, _RIGHT),
    TaxColumn("losses_used", "custom_losses_used", ColumnKind.MONEY, _RIGHT),
    TaxColumn("allowance_used", "custom_allowance_used", ColumnKind.MONEY, _RIGHT),
    TaxColumn("taxable", "custom_taxable", ColumnKind.MONEY, _RIGHT),
    TaxColumn("gains_tax", "custom_gains_tax", ColumnKind.MONEY, _RIGHT),
    TaxColumn("income", "ch_income", ColumnKind.MONEY, _RIGHT),
    TaxColumn("income_tax", "ch_income_tax", ColumnKind.MONEY, _RIGHT),
    TaxColumn("withheld", "tax_withheld", ColumnKind.MONEY, _RIGHT),
    TaxColumn("wealth", "ch_wealth", ColumnKind.MONEY, _RIGHT, none_label="ch_year_open"),
    TaxColumn("wealth_tax", "ch_wealth_tax", ColumnKind.MONEY, _RIGHT, none_label="ch_year_open"),
)
_LOSS_COLUMNS = (
    TaxColumn("year", "tax_year", ColumnKind.YEAR, _LEFT),
    TaxColumn("losses", "tax_amount", ColumnKind.MONEY, _RIGHT),
    TaxColumn("used", "tax_used", ColumnKind.MONEY, _RIGHT),
    TaxColumn("expired", "tax_expired", ColumnKind.MONEY, _RIGHT),
    TaxColumn("remaining", "tax_remaining", ColumnKind.MONEY, _RIGHT),
    TaxColumn("usable_until", "tax_usable_until", ColumnKind.DATE, _RIGHT),
)
_RATE_COLUMNS = (
    TaxColumn("item", "", ColumnKind.LABEL, _LEFT),
    TaxColumn("value", "value", ColumnKind.SHARE, _RIGHT),
)
_AMOUNT_COLUMNS = (
    TaxColumn("item", "", ColumnKind.LABEL, _LEFT),
    TaxColumn("value", "value", ColumnKind.MONEY, _RIGHT),
)


@dataclass
class _Lot:
    year: int
    amount: Decimal
    used: Decimal = Decimal(0)


@dataclass
class _Balance:
    """Net losses by year, usable for ``carry`` following years, oldest first."""

    carry: int
    lots: list[_Lot] = field(default_factory=list)

    def use(self, amount: Decimal, year: int) -> Decimal:
        used = Decimal(0)
        for lot in self.lots:
            usable = lot.year < year <= lot.year + self.carry
            free = lot.amount - lot.used
            if not usable or free <= 0 or used >= amount:
                continue
            take = min(free, amount - used)
            lot.used += take
            used += take
        return used

    def rows(self, as_of: date) -> tuple[Row, ...]:
        rows = []
        for lot in self.lots:
            free = lot.amount - lot.used
            expired = free if as_of.year > lot.year + self.carry else Decimal(0)
            rows.append(
                (
                    lot.year,
                    lot.amount,
                    lot.used,
                    expired,
                    free - expired,
                    date(lot.year + self.carry, 12, 31),
                )
            )
        return tuple(rows)

    def remaining(self, as_of: date) -> Decimal:
        return sum((Decimal(str(r[4])) for r in self.rows(as_of)), Decimal(0))


@dataclass(frozen=True)
class _Year:
    year: int
    result: Decimal
    exempt: Decimal
    taxable_gains: Decimal
    taxable_losses: Decimal
    losses_used: Decimal
    allowance_used: Decimal
    taxable: Decimal
    gains_tax: Decimal
    income: Decimal
    income_tax: Decimal
    withheld: Decimal
    wealth: Decimal | None
    wealth_tax: Decimal | None

    def row(self) -> Row:
        return (
            self.year, self.result, self.exempt, self.taxable_gains, self.taxable_losses,
            self.losses_used, self.allowance_used, self.taxable, self.gains_tax, self.income,
            self.income_tax, self.withheld, self.wealth, self.wealth_tax,
        )  # fmt: skip


class _Report:
    def __init__(self, inputs: TaxInputs, settings: CustomSettings) -> None:
        self.inputs = inputs
        self.settings = settings
        days = [t.trade_date for t in inputs.transactions]
        first = min(days).year if days else inputs.as_of.year
        self.years = range(first, inputs.as_of.year + 1)
        self.sales: dict[tuple[date, str, str, Decimal], list[FifoSale]] = {}
        for sale in fifo_sales(inputs.transactions):
            key = (sale.sold, sale.account, sale.isin, sale.quantity)
            self.sales.setdefault(key, []).append(sale)
        self.balance = _Balance(settings.loss_carry_years)

    def build(self) -> TaxReport:
        rows = [self._year(year) for year in self.years]
        s = self.settings
        paragraphs = [
            Paragraph("custom_intro", (("description", s.description),)),
            Paragraph("custom_order"),
            Paragraph(
                "custom_losses_netted" if s.losses == "netted" else "custom_losses_ignored",
                (("years", str(s.loss_carry_years)),),
            ),
            Paragraph("custom_exempt", (("months", str(s.exempt_after_months)),))
            if s.exempt_after_months
            else Paragraph("custom_no_exempt"),
            Paragraph("custom_withheld"),
            Paragraph("tax_sources", (("sources", SourcesRef()),)),
        ]
        tables = [
            TaxTable(
                "custom_settings",
                _RATE_COLUMNS,
                (
                    ("custom_gains_rate", s.gains_rate),
                    ("custom_income_rate", s.income_rate),
                    ("custom_wealth_tax_rate", s.wealth_tax_rate),
                ),
            ),
            TaxTable("custom_amounts", _AMOUNT_COLUMNS, (("custom_allowance", s.gains_allowance),)),
            TaxTable(
                "custom_years",
                _YEAR_COLUMNS,
                tuple(r.row() for r in rows),
                file="custom_years",
                index="year",
                note="custom_years_note",
            ),
        ]
        if s.losses == "netted":
            tables.append(
                TaxTable(
                    "tax_losses",
                    _LOSS_COLUMNS,
                    self.balance.rows(self.inputs.as_of),
                    file="custom_losses",
                    index="year",
                    shown_when_empty=False,
                )
            )
        return TaxReport(
            country="custom",
            as_of=self.inputs.as_of,
            checked_on=self.inputs.as_of,
            sources=_SOURCES,
            paragraphs=tuple(paragraphs),
            tables=tuple(tables),
            scalars=self._scalars(rows),
            title="custom_title",
            notice=NOTICE,
        )

    # ------------------------------------------------------------------ per year
    def _exempt_share(self, gain: RealisedGain) -> Decimal:
        months = self.settings.exempt_after_months
        if months == 0:
            return Decimal(0)
        key = (gain.trade_date, gain.account, gain.isin.code, gain.quantity)
        sale = self.sales[key].pop(0)
        return sale.units_held(months) / sale.quantity

    def _year(self, year: int) -> _Year:
        s, inputs = self.settings, self.inputs
        gains = [
            g
            for g in inputs.history.realised
            if g.trade_date.year == year and g.trade_date <= inputs.as_of
        ]
        result = exempt = taxable_gains = taxable_losses = Decimal(0)
        for gain in gains:
            share = self._exempt_share(gain)
            part = gain.gain_base * share
            taxable = gain.gain_base - part
            result += gain.gain_base
            exempt += part
            if taxable > 0:
                taxable_gains += taxable
            else:
                taxable_losses -= taxable
        used = Decimal(0)
        if s.losses == "ignored":
            base = taxable_gains
        else:
            net = taxable_gains - taxable_losses
            if net < 0:
                self.balance.lots.append(_Lot(year, -net))
                base = Decimal(0)
            else:
                used = self.balance.use(net, year)
                base = net - used
        allowance = min(s.gains_allowance, base)
        taxable_base = base - allowance
        income = [i for i in inputs.history.income if i.trade_date.year == year]
        gross = sum((i.gross_base for i in income if i.trade_date <= inputs.as_of), Decimal(0))
        withheld = sum((i.taxes_base for i in income if i.trade_date <= inputs.as_of), Decimal(0))
        wealth = self._wealth(year)
        return _Year(
            year=year,
            result=result,
            exempt=exempt,
            taxable_gains=taxable_gains,
            taxable_losses=taxable_losses,
            losses_used=used,
            allowance_used=allowance,
            taxable=taxable_base,
            gains_tax=_cents(s.gains_rate * taxable_base),
            income=gross,
            income_tax=_cents(s.income_rate * gross),
            withheld=withheld,
            wealth=wealth,
            wealth_tax=None if wealth is None else _cents(s.wealth_tax_rate * wealth),
        )

    def _wealth(self, year: int) -> Decimal | None:
        end = date(year, 12, 31)
        if end > self.inputs.as_of:
            return None
        known = [d for d in self.inputs.valuation.totals if d <= end]
        return self.inputs.valuation.totals[max(known)] if known else None

    def _scalars(self, rows: Sequence[_Year]) -> dict[str, Decimal]:
        """Return the latest complete calendar year's taxes (the current one if none)."""
        as_of = self.inputs.as_of
        latest = as_of.year if date(as_of.year, 12, 31) <= as_of else as_of.year - 1
        row = next((r for r in rows if r.year == latest), rows[-1])
        scalars = {
            "gains_tax_estimate": row.gains_tax,
            "income_tax_estimate": row.income_tax,
        }
        if row.wealth_tax is not None:
            scalars["wealth_tax_estimate"] = row.wealth_tax
        scalars["losses_remaining"] = self.balance.remaining(as_of)
        return scalars


# --------------------------------------------------------------------------- helpers
def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def _rate(table: Mapping[str, object], key: str) -> Decimal:
    value = table[key]
    if type(value) not in (int, float) or not 0 <= value < 1:  # type: ignore[operator]
        raise ValidationError(f"{key} must be a number in [0, 1), got {value!r}")
    return Decimal(repr(value))


def _whole(table: Mapping[str, object], key: str) -> int:
    value = table[key]
    if type(value) is not int or value < 0:
        raise ValidationError(f"{key} must be an int >= 0, got {value!r}")
    return value
