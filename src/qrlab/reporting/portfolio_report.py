"""The portfolio report: a formatted view of verified ledger, valuation and performance results.

The report computes nothing new. Every number comes from a tested function in
:mod:`qrlab.portfolio` or :mod:`qrlab.metrics`, so the report can only be as right or wrong as
those. It states its data dates, provenance, assumptions and every carried-forward value, shows
warnings in a visible box, and ends with a "not investment advice" notice.

Reports built from real data contain personal financial information: write them only to
git-ignored folders and do not publish them.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.errors import DataNotFoundError
from qrlab.data.provenance import Provenance
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import Instrument
from qrlab.metrics.drawdown import drawdown_series, max_drawdown
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.performance import annualised_volatility
from qrlab.portfolio.ledger import LedgerHistory, ToBase
from qrlab.portfolio.performance import (
    FlowTiming,
    TwrResult,
    XirrResult,
    external_flows_by_date,
    money_weighted_return,
    pnl_breakdown,
    time_weighted_returns,
)
from qrlab.portfolio.valuation import PriceSeries, Valuation
from qrlab.reporting.figures import AxisFormat, line_figure
from qrlab.reporting.formatting import (
    Language,
    NumberStyle,
    format_date,
    format_money,
    format_number,
    format_percent,
    style_for,
)
from qrlab.reporting.html import Figure, Report, Section
from qrlab.reporting.labels import label
from qrlab.reporting.tables import Table

__all__ = ["build_portfolio_report"]

ONE_YEAR_DAYS = 365


def build_portfolio_report(
    *,
    name: str,
    history: LedgerHistory,
    valuation: Valuation,
    prices: Mapping[Isin, PriceSeries],
    to_base: ToBase,
    language: Language,
    generated_at: datetime,
    flow_timing: FlowTiming,
    max_price_age_days: int,
    fx_description: str,
    provenance: Sequence[Provenance],
    instruments: Mapping[Isin, Instrument],
    import_notes: Sequence[str],
    return_frequency: tuple[Frequency, float] | None,
) -> Report:
    """Build the portfolio report.

    Parameters
    ----------
    name
        Portfolio name shown in the title.
    history, valuation, prices, to_base
        Ledger history, its valuation, the price series and the converter used for it.
    language
        Report language (labels and number style).
    generated_at
        Timezone-aware generation time (explicit, so output is reproducible).
    flow_timing
        Convention for the TWR.
    max_price_age_days
        Price staleness limit used for the valuation (reported as an assumption).
    fx_description
        Plain-text description of the FX source, e.g. "ECB reference rates, max age 3 days".
    provenance
        Provenance of every input file (transactions, prices, FX, master data).
    instruments
        Master data used for names; missing entries produce a warning.
    import_notes
        Notes from the broker import (e.g. row reversal).
    return_frequency
        ``(frequency, periods_per_year)`` if the valuation dates are regular; enables the
        annualised volatility. ``None`` omits it, with a note.
    """
    if generated_at.utcoffset() is None:
        raise ValidationError("generated_at must be timezone-aware")
    return _Builder(
        name, history, valuation, prices, to_base, language, generated_at, flow_timing,
        max_price_age_days, fx_description, provenance, instruments, import_notes, return_frequency,
    ).build()  # fmt: skip


class _Builder:
    def __init__(
        self,
        name: str,
        history: LedgerHistory,
        valuation: Valuation,
        prices: Mapping[Isin, PriceSeries],
        to_base: ToBase,
        language: Language,
        generated_at: datetime,
        flow_timing: FlowTiming,
        max_price_age_days: int,
        fx_description: str,
        provenance: Sequence[Provenance],
        instruments: Mapping[Isin, Instrument],
        import_notes: Sequence[str],
        return_frequency: tuple[Frequency, float] | None,
    ) -> None:
        self.name = name
        self.history = history
        self.valuation = valuation
        self.prices = prices
        self.to_base = to_base
        self.language = language
        self.style: NumberStyle = style_for(language)
        self.generated_at = generated_at
        self.flow_timing = flow_timing
        self.max_price_age_days = max_price_age_days
        self.fx_description = fx_description
        self.provenance = list(provenance)
        self.instruments = instruments
        self.import_notes = list(import_notes)
        self.return_frequency = return_frequency
        self.dates = list(valuation.totals)
        if not self.dates:
            raise ValidationError("the valuation has no dates")
        self.start, self.end = self.dates[0], self.dates[-1]
        self.warnings: list[str] = []

    # ----------------------------------------------------------------- helpers
    def t(self, key: str, **values: str) -> str:
        return label(key, self.language, **values)

    def money(self, amount: Decimal) -> str:
        return format_money(Money(amount, self.history.base), style=self.style)

    def pct(self, value: float) -> str:
        return format_percent(value, 2, style=self.style)

    def day(self, value: date) -> str:
        return format_date(value, language=self.language)

    # ----------------------------------------------------------------- build
    def build(self) -> Report:
        flows = external_flows_by_date(self.history)
        twr = time_weighted_returns(self.valuation, flows, flow_timing=self.flow_timing)
        mwr = self._mwr()
        sections = (
            self._summary(flows, twr, mwr),
            self._positions(),
            self._cash(),
            self._pnl(),
            self._income_costs(),
            self._figures(flows, twr),
            self._data(),
        )
        self._collect_warnings(twr, mwr)
        facts = (
            (self.t("base_currency"), self.history.base.code),
            (self.t("period"), f"{self.day(self.start)} - {self.day(self.end)}"),
            (self.t("as_of"), self.day(self.end)),
            (self.t("generated_at"), self.generated_at.strftime("%Y-%m-%d %H:%M %Z")),
        )
        version = importlib.metadata.version("quant-research-lab")
        footer = (
            self.t("disclaimer"),
            self.t("private_reminder"),
            f"{self.t('version')}: {version}",
        )
        return Report(
            title=f"{self.t('report_title')}: {self.name}",
            language=self.language,
            facts=facts,
            warnings=tuple(self.warnings),
            sections=sections,
            footer=footer,
        )

    def _mwr(self) -> XirrResult | None:
        try:
            return money_weighted_return(self.history, self.valuation, end=self.end)
        except UndefinedMetricError:
            return None

    def _summary(
        self, flows: Mapping[date, Decimal], twr: TwrResult, mwr: XirrResult | None
    ) -> Section:
        end_value = self.valuation.totals[self.end]
        net_flows = sum(flows.values(), Decimal(0))
        pnl = end_value - net_flows
        rows: list[tuple[str, str]] = [
            (self.t("end_value"), self.money(end_value)),
            (self.t("net_flows"), self.money(net_flows)),
            (self.t("pnl"), self.money(pnl)),
        ]
        paragraphs: list[str] = []
        if len(twr.returns) == 0:
            paragraphs.append(self.t("not_enough_dates"))
        else:
            rows.append((self.t("twr"), self.pct(twr.total)))
            days = (self.end - self.start).days
            if days >= ONE_YEAR_DAYS:
                annual = (1.0 + twr.total) ** (ONE_YEAR_DAYS / days) - 1.0
                rows.append((self.t("twr_annualised"), self.pct(annual)))
            else:
                paragraphs.append(self.t("not_annualised"))
            rows.append((self.t("max_drawdown"), self.pct(max_drawdown(twr.returns))))
            if self.return_frequency is not None and len(twr.returns) >= 2:
                _, periods = self.return_frequency
                volatility = annualised_volatility(twr.returns, periods_per_year=periods)
                rows.append((self.t("volatility"), self.pct(volatility)))
            else:
                paragraphs.append(self.t("volatility_omitted"))
        rows.append((self.t("mwr"), self.t("not_available") if mwr is None else self.pct(mwr.rate)))
        paragraphs += [self.t("twr_definition"), self.t("mwr_definition"), self.t("not_comparable")]
        table = Table(
            title=self.t("summary"),
            columns=("", self.t("value")),
            rows=tuple(rows),
            align=("left", "right"),
            notes=(),
        )
        return Section(self.t("summary"), tuple(paragraphs), (table,), ())

    def _positions(self) -> Section:
        state = self.history.state_on(self.end)
        total = self.valuation.totals[self.end]
        values = self.valuation.positions[self.end]
        rows = []
        for key, value in sorted(values.items(), key=lambda item: (-item[1], item[0][1].code)):
            account, isin = key
            position = state.positions[key]
            if isin not in self.prices:
                raise DataNotFoundError(f"no price series for {isin.code} in the report inputs")
            price, used = self.prices[isin].price_on(self.end, self.max_price_age_days)
            instrument = self.instruments.get(isin)
            rows.append(
                (
                    account,
                    isin.code,
                    instrument.name if instrument else isin.code,
                    format_number(position.quantity, 4, style=self.style)
                    .rstrip("0")
                    .rstrip(self.style.decimal),
                    format_number(price, 4, style=self.style),
                    self.day(used),
                    position.currency.code,
                    self.money(value),
                    self.pct(float(value / total)) if total else self.t("not_available"),
                    self.money(position.cost_base),
                    self.money(value - position.cost_base),
                )
            )
        columns = (
            self.t("account"), self.t("isin"), self.t("name"), self.t("quantity"), self.t("price"),
            self.t("price_date"), self.t("currency"), self.t("value"), self.t("weight"),
            self.t("cost_basis"), self.t("unrealised"),
        )  # fmt: skip
        align = (
            "left",
            "left",
            "left",
            "right",
            "right",
            "left",
            "left",
            "right",
            "right",
            "right",
            "right",
        )
        table = Table(self.t("positions"), columns, tuple(rows), align, ())
        return Section(self.t("positions"), (), (table,), ())

    def _cash(self) -> Section:
        state = self.history.state_on(self.end)
        rows = []
        for (account, currency), balance in sorted(
            state.cash.items(), key=lambda i: (i[0][0], i[0][1].code)
        ):
            local = Money(balance, currency)
            base = self.to_base(local, self.end).amount
            rows.append(
                (account, currency.code, format_money(local, style=self.style), self.money(base))
            )
        columns = (
            self.t("account"),
            self.t("currency"),
            self.t("local_amount"),
            self.t("base_amount"),
        )
        table = Table(self.t("cash"), columns, tuple(rows), ("left", "left", "right", "right"), ())
        return Section(self.t("cash"), (), (table,), ())

    def _pnl(self) -> Section:
        pnl = pnl_breakdown(self.history, self.valuation, self.to_base, start=None, end=self.end)
        self.residual = pnl.residual
        rows = (
            (self.t("realised"), self.money(pnl.realised)),
            (self.t("unrealised_change"), self.money(pnl.unrealised_change)),
            (self.t("income"), self.money(pnl.income)),
            (self.t("costs"), self.money(-pnl.costs)),
            (self.t("cash_fx"), self.money(pnl.cash_fx)),
            (self.t("residual"), self.money(pnl.residual)),
            (self.t("pnl"), self.money(pnl.total)),
        )
        table = Table(self.t("pnl_breakdown"), ("", self.t("value")), rows, ("left", "right"), ())
        return Section(self.t("pnl_breakdown"), (), (table,), ())

    def _income_costs(self) -> Section:
        entries: list[tuple[date, str, str, Decimal]] = []
        for income in self.history.income:
            name = income.isin.code if income.isin else ""
            entries.append((income.trade_date, income.kind.value, name, income.net_base))
        for cost in self.history.costs:
            entries.append((cost.trade_date, cost.kind.value, "", -cost.amount_base))
        rows = tuple(
            (self.day(d), self.t(f"kind_{kind}"), isin, self.money(amount))
            for d, kind, isin, amount in sorted(entries, key=lambda e: e[0])
        )
        columns = (self.t("date"), self.t("kind"), self.t("isin"), self.t("amount"))
        notes = () if rows else (self.t("none"),)
        table = Table(
            self.t("income_costs"), columns, rows, ("left", "left", "left", "right"), notes
        )
        return Section(self.t("income_costs"), (), (table,), ())

    def _figures(self, flows: Mapping[date, Decimal], twr: TwrResult) -> Section:
        values = self.valuation.series()
        figures = [
            Figure(
                self.t("figure_value"),
                line_figure(
                    [(self.t("value"), values)],
                    title=self.t("figure_value"),
                    y_label=self.history.base.code,
                    axis=AxisFormat.NUMBER,
                    style=self.style,
                    markers=sorted(flows),
                    marker_label=self.t("flows_marker"),
                ),
            )
        ]
        if len(twr.returns):
            cumulative = (1.0 + twr.returns).cumprod() - 1.0
            figures.append(
                Figure(
                    self.t("figure_twr"),
                    line_figure(
                        [("TWR", cumulative)],
                        title=self.t("figure_twr"),
                        y_label="",
                        axis=AxisFormat.PERCENT,
                        style=self.style,
                    ),
                )
            )
            drawdown = drawdown_series(twr.returns)
            figures.append(
                Figure(
                    self.t("figure_drawdown"),
                    line_figure(
                        [(self.t("figure_drawdown"), drawdown)],
                        title=self.t("figure_drawdown"),
                        y_label="",
                        axis=AxisFormat.PERCENT,
                        style=self.style,
                    ),
                )
            )
        return Section(self.t("figures"), (), (), tuple(figures))

    def _data(self) -> Section:
        sources = Table(
            self.t("sources"),
            (
                self.t("source"),
                self.t("dataset"),
                self.t("retrieved"),
                self.t("sha256"),
                self.t("terms"),
            ),
            tuple(
                (
                    p.source,
                    p.dataset,
                    self.day(p.retrieved_at.date()),
                    p.sha256[:12],
                    p.terms,
                )
                for p in self.provenance
            ),
            ("left",) * 5,
            () if self.provenance else (self.t("none"),),
        )
        timing = (
            "timing_start_of_day"
            if self.flow_timing is FlowTiming.START_OF_DAY
            else "timing_end_of_day"
        )
        assumptions = Table(
            self.t("assumptions"),
            ("", self.t("value")),
            (
                (self.t("flow_timing"), self.t(timing)),
                (self.t("cost_basis_method"), self.t("cost_basis_value")),
                (self.t("fx_source"), self.fx_description),
                (self.t("price_staleness"), str(self.max_price_age_days)),
            ),
            ("left", "left"),
            (),
        )
        carried = [
            (isin.code, self.day(requested), self.day(used))
            for isin, requested, used in self.valuation.stale_prices
        ] + [
            (currency.code, self.day(requested), self.day(used))
            for currency, requested, used in _fx_stale_uses(self.to_base)
        ]
        carried_table = Table(
            self.t("carried_forward"),
            ("", self.t("requested_date"), self.t("used_date")),
            tuple(carried),
            ("left", "left", "left"),
            () if carried else (self.t("none"),),
        )
        paragraphs = tuple(f"{self.t('import_notes')}: {note}" for note in self.import_notes)
        return Section(
            self.t("data_assumptions"), paragraphs, (sources, assumptions, carried_table), ()
        )

    def _collect_warnings(self, twr: TwrResult, mwr: XirrResult | None) -> None:
        for isin, requested, used in self.valuation.stale_prices:
            self.warnings.append(
                self.t(
                    "warn_stale_price",
                    isin=isin.code,
                    requested=self.day(requested),
                    used=self.day(used),
                )
            )
        for currency, requested, used in _fx_stale_uses(self.to_base):
            self.warnings.append(
                self.t(
                    "warn_stale_fx",
                    currency=currency.code,
                    requested=self.day(requested),
                    used=self.day(used),
                )
            )
        if self.residual != 0:
            self.warnings.append(self.t("warn_residual", value=self.money(self.residual)))
        if mwr is not None and len(mwr.candidates) > 1:
            rates = ", ".join(self.pct(r) for r in mwr.candidates)
            self.warnings.append(self.t("warn_mwr_roots", rates=rates))
        held = {isin for _, isin in self.history.state_on(self.end).positions}
        for isin in sorted(held - set(self.instruments), key=lambda i: i.code):
            self.warnings.append(self.t("warn_missing_master", isin=isin.code))
        skipped = [d for d in twr.skipped if d != self.start]
        if skipped:
            self.warnings.append(
                self.t("warn_skipped", dates=", ".join(self.day(d) for d in skipped))
            )


def _fx_stale_uses(to_base: ToBase) -> tuple[tuple[Currency, date, date], ...]:
    """Carried-forward FX uses, if the converter records them (e.g. ``EcbConverter``)."""
    uses: tuple[tuple[Currency, date, date], ...] = tuple(getattr(to_base, "stale_uses", ()))
    return uses
