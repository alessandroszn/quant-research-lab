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
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from qrlab.checks.engine import ALL_CHECKS, CheckResult
from qrlab.checks.framework import Direction, Finding, MeasureUnit, Severity
from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.errors import DataNotFoundError
from qrlab.data.provenance import Provenance
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import Instrument
from qrlab.lookthrough.exposures import (
    CASH,
    NOT_LOOKED_THROUGH,
    SPECIAL_BUCKETS,
    UNEXPLAINED,
    UNKNOWN,
    Dimension,
    WeightTreatment,
)
from qrlab.lookthrough.inputs import LookThroughInputs
from qrlab.lookthrough.tracking import td_vs_ter, tracking_difference
from qrlab.metrics.drawdown import drawdown_series, max_drawdown
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.performance import SharpeEstimate, annualised_volatility
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
from qrlab.reporting.check_labels import check_label
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
from qrlab.reporting.messages import detail_key, detail_value, is_known, translate
from qrlab.reporting.tables import Table
from qrlab.scenarios.definitions import HistoricalScenario
from qrlab.scenarios.summary import RiskSummary
from qrlab.simulation.outcomes import ProjectionResult
from qrlab.simulation.plan import Flow
from qrlab.tax.regime import (
    Cell,
    ColumnKind,
    Holdings,
    LabelRef,
    ParagraphValue,
    SourcesRef,
    TaxColumn,
    TaxReport,
    TaxTable,
)

__all__ = ["RiskFreeSummary", "build_portfolio_report"]

ONE_YEAR_DAYS = 365
TOP_BUCKETS = 10


@dataclass(frozen=True)
class RiskFreeSummary:
    """A risk-free series over the report's TWR periods, and the Sharpe ratio it gives.

    Parameters
    ----------
    source
        Name of the series, e.g. ``"€STR (ECB)"``.
    total
        Compounded risk-free return over all TWR periods.
    sharpe
        Annualised Sharpe ratio of the TWR returns in excess of the series, or ``None``.
    reason
        Why ``sharpe`` is ``None`` (empty otherwise).
    """

    source: str
    total: float
    sharpe: SharpeEstimate | None
    reason: str = ""


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
    checks: CheckResult | None,
    lookthrough: LookThroughInputs | None,
    risk: RiskSummary | None,
    projection: ProjectionResult | None,
    risk_free: RiskFreeSummary | None,
    tax: TaxReport | None,
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
    checks
        Health-check result on the report's last valuation date (see :mod:`qrlab.checks`), or
        ``None`` to say in the report that checks were not run. A result for another date
        raises.
    lookthrough
        Exposures through fund holdings on the last valuation date, with the holdings and
        tracking series, or ``None`` to say in the report that look-through was not done.
    risk
        Risk numbers and stress-test results on the last valuation date, or ``None`` to say
        in the report that they were not computed.
    projection
        A projection of the portfolio with its sensitivity table, or ``None`` to say in the
        report that it was not computed.
    risk_free
        A risk-free series over the TWR periods and the Sharpe ratio it gives, or ``None``:
        the summary then shows no Sharpe ratio.
    tax
        A country's tax analytics of the account (:class:`qrlab.tax.TaxReport`, e.g. from
        :func:`qrlab.tax.italian_tax_report`), or ``None``: the report then has no tax
        section. The section is rendered from the report's description alone (phase 9.1).
    """
    if generated_at.utcoffset() is None:
        raise ValidationError("generated_at must be timezone-aware")
    return _Builder(
        name, history, valuation, prices, to_base, language, generated_at, flow_timing,
        max_price_age_days, fx_description, provenance, instruments, import_notes, return_frequency,
        checks,
        lookthrough,
        risk,
        projection,
        risk_free,
        tax,
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
        checks: CheckResult | None,
        lookthrough: LookThroughInputs | None,
        risk: RiskSummary | None,
        projection: ProjectionResult | None,
        risk_free: RiskFreeSummary | None,
        tax: TaxReport | None,
    ) -> None:
        self.risk_free = risk_free
        self.tax = tax
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
        if checks is not None and checks.as_of != self.end:
            raise ValidationError(
                f"health checks are as of {checks.as_of}, the report ends on {self.end}"
            )
        self.checks = checks
        if lookthrough is not None and lookthrough.exposures.as_of != self.end:
            dated = lookthrough.exposures.as_of
            raise ValidationError(f"look-through is as of {dated}, the report ends on {self.end}")
        self.lookthrough = lookthrough
        if risk is not None and risk.as_of != self.end:
            raise ValidationError(f"risk is as of {risk.as_of}, the report ends on {self.end}")
        self.risk = risk
        if projection is not None and projection.summary.dates[0] != self.end:
            raise ValidationError(
                f"projection starts on {projection.summary.dates[0]}, the report ends on {self.end}"
            )
        self.projection = projection
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
            self._lookthrough(),
            self._risk(),
            self._projection(),
            *(() if self.tax is None else (self._tax(self.tax),)),
            self._health_checks(),
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
            if self.risk_free is not None:
                rows.append(
                    (
                        self.t("risk_free_total", source=self.risk_free.source),
                        self.pct(self.risk_free.total),
                    )
                )
                sharpe = self.risk_free.sharpe
                if sharpe is None:
                    rows.append((self.t("sharpe"), self.t("not_available")))
                    reason = translate(self.risk_free.reason, self.language)
                    paragraphs.append(self.t("sharpe_missing", reason=reason))
                else:
                    value = self.t(
                        "sharpe_value",
                        value=format_number(sharpe.value, 2, style=self.style),
                        se=format_number(sharpe.standard_error, 2, style=self.style),
                        n=str(sharpe.n),
                    )
                    rows.append((self.t("sharpe"), value))
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
        transfers = ((self.t("transfers"), self.money(pnl.transfers)),) if pnl.transfers else ()
        rows = (
            (self.t("realised"), self.money(pnl.realised)),
            (self.t("unrealised_change"), self.money(pnl.unrealised_change)),
            (self.t("income"), self.money(pnl.income)),
            (self.t("costs"), self.money(-pnl.costs)),
            (self.t("cash_fx"), self.money(pnl.cash_fx)),
            *transfers,
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
        paragraphs = tuple(
            f"{self.t('import_notes')}: {translate(note, self.language)}"
            for note in self.import_notes
        )
        return Section(
            self.t("data_assumptions"), paragraphs, (sources, assumptions, carried_table), ()
        )

    def _risk(self) -> Section:
        if self.risk is None:
            return Section(self.t("risk_stress"), (self.t("risk_not_computed"),), (), ())
        risk = self.risk
        paragraphs = (
            self.t(
                "risk_window",
                frequency=risk.frequency,
                start=self.day(risk.window_start),
                end=self.day(risk.window_end),
                n=str(risk.n_obs),
            ),
            self.t("stress_note"),
        )
        vol = risk.volatility
        rows = [
            (self._name_of(holding), self.pct(float(vol.component[holding])),
             self.pct(float(vol.share[holding])))
            for holding in vol.component.index
        ]  # fmt: skip
        rows.append((self.t("total"), self.pct(vol.total), self.pct(1.0)))
        tables = [
            Table(
                self.t("risk_volatility"),
                (self.t("holding"), self.t("contribution"), self.t("share")),
                tuple(rows),
                ("left", "right", "right"),
                (),
            )
        ]
        if risk.var_es:
            confidence = self.pct(risk.confidence)
            tables.append(
                Table(
                    self.t("risk_var_es", confidence=confidence),
                    (self.t("method"), "VaR", "ES"),
                    tuple((m, self.pct(v), self.pct(e)) for m, (v, e) in risk.var_es.items()),
                    ("left", "right", "right"),
                    (self.t("var_note"),),
                )
            )
        if risk.scenarios:
            summary = []
            detail = []
            for result in risk.scenarios:
                scenario = result.scenario
                dates = (
                    f"{self.day(result.first_date)} - {self.day(result.last_date)}"
                    if result.first_date is not None and result.last_date is not None
                    else self.t("not_available")
                )
                kind = "historical" if isinstance(scenario, HistoricalScenario) else "hypothetical"
                summary.append(
                    (
                        scenario.description,
                        self.t(f"scenario_{kind}"),
                        dates,
                        self.pct(result.portfolio_return),
                        self.money(result.pnl.amount),
                        self.pct(result.not_covered_weight),
                    )
                )
                for row in result.rows:
                    detail.append(
                        (
                            scenario.id,
                            self._name_of(row.holding),
                            self.t(f"method_{row.method.replace(' ', '_')}"),
                            self.t("not_available")
                            if row.base_return is None
                            else self.pct(row.base_return),
                            self.t("not_available")
                            if row.contribution is None
                            else self.pct(row.contribution),
                        )
                    )
            tables.append(
                Table(
                    self.t("scenarios"),
                    (
                        self.t("scenario"),
                        self.t("kind"),
                        self.t("dates_used"),
                        self.t("portfolio_return"),
                        self.t("pnl"),
                        self.t("not_covered"),
                    ),
                    tuple(summary),
                    ("left", "left", "left", "right", "right", "right"),
                    (self.t("not_covered_note"),),
                )
            )
            tables.append(
                Table(
                    self.t("scenario_detail"),
                    (
                        self.t("scenario"),
                        self.t("holding"),
                        self.t("method"),
                        self.t("base_return"),
                        self.t("contribution"),
                    ),
                    tuple(detail),
                    ("left", "left", "left", "right", "right"),
                    (),
                )
            )
        return Section(self.t("risk_stress"), paragraphs, tuple(tables), ())

    def _projection(self) -> Section:
        if self.projection is None:
            return Section(self.t("projection"), (self.t("projection_not_computed"),), (), ())
        summary = self.projection.summary
        plan = summary.plan
        years = (len(summary.dates) - 1) / plan.periods_per_year
        rebalancing = (
            self.t("rebalance_never")
            if plan.rebalance_every is None
            else self.t("rebalance_every", n=str(plan.rebalance_every))
        )
        assumptions = (
            (self.t("engine"), summary.engine),
            (self.t("paths"), format_number(summary.n_paths, 0, style=self.style)),
            (self.t("horizon"), self.t("years", n=format_number(years, 1, style=self.style))),
            (self.t("initial_wealth"), self.money(Decimal(repr(plan.initial_wealth)))),
            (self.t("flows"), "; ".join(self._flow_text(f) for f in plan.flows) or self.t("none")),
            (self.t("flow_timing"), self.t(f"timing_{plan.flow_timing}_of_period")),
            (self.t("rebalancing"), rebalancing),
            (self.t("annual_cost"), self.pct(plan.annual_cost)),
            (self.t("inflation"), self.pct(plan.inflation)),
            (self.t("capital_gains_tax"), self.pct(plan.taxes.capital_gains_rate)),
            (self.t("wealth_tax"), self.pct(plan.taxes.wealth_tax_rate)),
        )
        tables = [
            Table(self.t("assumptions"), ("", self.t("value")), assumptions, ("left", "right"), ())
        ]
        terminal = tuple(
            (
                f"P{format_number(level, 0, style=self.style)}",
                self.money(Decimal(repr(real))),
                self.money(Decimal(repr(nominal))),
                self.money(Decimal(repr(after_tax))),
            )
            for level, real, nominal, after_tax in zip(
                summary.percentiles,
                summary.terminal_real,
                summary.terminal_nominal,
                summary.terminal_after_tax,
                strict=True,
            )
        )
        tables.append(
            Table(
                self.t("terminal_wealth"),
                (self.t("percentile"), self.t("real"), self.t("nominal"), self.t("after_tax")),
                terminal,
                ("left", "right", "right", "right"),
                (self.t("after_tax_note"),),
            )
        )
        depletion = (
            self.t("not_available")
            if summary.median_depletion_period is None
            else format_number(summary.median_depletion_period, 0, style=self.style)
        )
        odds = (
            (
                self.t("goal", goal=self.money(Decimal(repr(summary.goal_real)))),
                f"{self.pct(summary.p_goal)} ± {self.pct(summary.p_goal_se)}",
            ),
            (
                self.t("depletion"),
                f"{self.pct(summary.p_depleted)} ± {self.pct(summary.p_depleted_se)}",
            ),
            (self.t("median_depletion"), depletion),
            (
                self.t("mean_terminal_real"),
                f"{self.money(Decimal(repr(summary.terminal_mean_real)))} ± "
                f"{self.money(Decimal(repr(summary.terminal_mean_real_se)))}",
            ),
            (
                self.t("sequence_worst", n=str(summary.early_periods)),
                self.money(Decimal(repr(summary.sequence_worst))),
            ),
            (
                self.t("sequence_best", n=str(summary.early_periods)),
                self.money(Decimal(repr(summary.sequence_best))),
            ),
        )
        tables.append(
            Table(
                self.t("probabilities"),
                ("", self.t("value")),
                odds,
                ("left", "right"),
                (self.t("se_note"),),
            )
        )
        if self.projection.sensitivity:
            rows = tuple(
                (
                    self.t(f"sens_{row.key}"),
                    f"{self.pct(row.p_goal)} ± {self.pct(row.p_goal_se)}",
                    self.money(Decimal(repr(row.median_terminal_real))),
                )
                for row in self.projection.sensitivity
            )
            tables.append(
                Table(
                    self.t("sensitivity"),
                    (self.t("assumption"), self.t("goal_probability"), self.t("median_real")),
                    rows,
                    ("left", "right", "right"),
                    (self.t("sensitivity_note"),),
                )
            )
        index = pd.DatetimeIndex([pd.Timestamp(d) for d in summary.dates])
        lines = [
            (f"P{format_number(level, 0, style=self.style)}", pd.Series(values, index=index))
            for level, values in zip(summary.percentiles, summary.fan_real, strict=True)
        ]
        figure = Figure(
            self.t("fan_chart"),
            line_figure(
                lines,
                title=self.t("fan_chart"),
                y_label=plan.currency.code,
                axis=AxisFormat.NUMBER,
                style=self.style,
            ),
        )
        paragraphs = (self.t("projection_note"), self.t("projection_costs_note"))
        return Section(self.t("projection"), paragraphs, tuple(tables), (figure,))

    def _flow_text(self, flow: Flow) -> str:
        amount = self.money(Decimal(repr(flow.amount)))
        return self.t(
            f"flow_{flow.kind}",
            amount=amount,
            first=str(flow.first + 1),
            last=str(flow.last + 1),
            indexed=self.t("indexed") if flow.indexed else self.t("fixed"),
        )

    def _name_of(self, holding: str) -> str:
        for isin, instrument in self.instruments.items():
            if isin.code == holding:
                return instrument.name
        if holding.startswith("cash "):
            return f"{self.t('cash')} {holding.removeprefix('cash ')}"
        return holding

    def _tax(self, report: TaxReport) -> Section:
        """Render a country's tax analytics from its description (:mod:`qrlab.tax.regime`)."""
        paragraphs = tuple(
            self.t(p.key, **{name: self._tax_value(value, report) for name, value in p.args})
            for p in report.paragraphs
        )
        tables = tuple(
            self._tax_table(table)
            for table in report.tables
            if table.rows or table.shown_when_empty
        )
        return Section(self.t(report.title), paragraphs, tables, ())

    def _tax_value(self, value: ParagraphValue, report: TaxReport) -> str:
        if isinstance(value, LabelRef):
            return self.t(value.key)
        if isinstance(value, Holdings):
            return ", ".join(self._name_of(code) for code in value.isins)
        if isinstance(value, SourcesRef):
            return "; ".join(report.sources[self.language.value])
        if isinstance(value, date):
            return self.day(value)
        return value

    def _tax_table(self, table: TaxTable) -> Table:
        return Table(
            self.t(table.title),
            tuple(self.t(c.label) if c.label else "" for c in table.columns),
            tuple(
                tuple(self._tax_cell(cell, c) for cell, c in zip(row, table.columns, strict=True))
                for row in table.rows
            ),
            tuple(c.align for c in table.columns),
            () if table.note is None else (self.t(table.note),),
        )

    def _tax_cell(self, cell: Cell, column: TaxColumn) -> str:
        kind, prefix = column.kind, column.prefix
        if cell is None:
            return self.t(column.none_label) if column.none_label else ""
        if kind is ColumnKind.DATE and isinstance(cell, date):
            return self.day(cell)
        if kind is ColumnKind.HOLDING:
            return self._name_of(str(cell))
        if kind is ColumnKind.LABEL:
            return self.t(f"{prefix}{cell}")
        if kind is ColumnKind.MONEY and isinstance(cell, Decimal):
            return self.money(cell)
        if kind is ColumnKind.SHARE and isinstance(cell, Decimal):
            return self.pct(float(cell))
        if kind is ColumnKind.NUMBER and isinstance(cell, Decimal):
            exponent = cell.as_tuple().exponent
            decimals = max(0, -exponent) if isinstance(exponent, int) else 0
            return format_number(cell, decimals, style=self.style)
        return str(cell)

    def _lookthrough(self) -> Section:
        if self.lookthrough is None:
            return Section(self.t("lookthrough"), (self.t("lookthrough_not_done"),), (), ())
        inputs = self.lookthrough
        exposures = inputs.exposures
        paragraphs = [
            self.t(
                "lt_as_reported"
                if exposures.treatment is WeightTreatment.AS_REPORTED
                else "lt_normalised"
            ),
            self.t("lt_buckets"),
        ]
        if not exposures.issuer_mapped:
            paragraphs.append(self.t("lt_no_issuer_map"))
        tables = []
        dates = tuple(
            (
                isin.code,
                self._name(isin),
                self.day(day),
                str((self.end - day).days),
            )
            for isin, day in sorted(exposures.snapshot_dates.items(), key=lambda i: i[0].code)
        )
        if dates:
            tables.append(
                Table(
                    self.t("holdings_dates"),
                    (self.t("isin"), self.t("name"), self.t("holdings_date"), self.t("age_days")),
                    dates,
                    ("left", "left", "left", "right"),
                    (),
                )
            )
        for dimension, key in (
            (Dimension.COUNTRY, "lt_country"),
            (Dimension.SECTOR, "lt_sector"),
            (Dimension.CURRENCY, "lt_currency"),
            (Dimension.SECURITY, "lt_security"),
        ):
            tables.append(self._exposure_table(dimension, key))
        overlaps = inputs.overlaps()
        if overlaps:
            rows = tuple(
                (p.first.code, p.second.code, self.pct(p.overlap), self.pct(p.by_name),
                 f"{self.pct(p.unmatched_first)} / {self.pct(p.unmatched_second)}")
                for p in overlaps
            )  # fmt: skip
            tables.append(
                Table(
                    self.t("lt_overlap"),
                    (
                        self.t("fund"),
                        self.t("fund"),
                        self.t("overlap"),
                        self.t("overlap_by_name"),
                        self.t("unmatched"),
                    ),
                    rows,
                    ("left", "left", "right", "right", "right"),
                    (self.t("lt_overlap_note"),),
                )
            )
        tracking = []
        for isin, (fund, index) in sorted(inputs.tracking.items(), key=lambda i: i[0].code):
            td = tracking_difference(fund, index)
            instrument = self.instruments.get(isin)
            ter = instrument.ter if instrument is not None else None
            na = self.t("not_available")
            tracking.append(
                (
                    isin.code,
                    f"{self.day(td.start)} - {self.day(td.end)}",
                    self.t(f"series_{fund.price_type.value}"),
                    self.pct(td.difference),
                    na if td.annualised is None else self.pct(td.annualised),
                    na if ter is None else self.pct(float(ter)),
                    na if td.annualised is None or ter is None
                    else self.pct(td_vs_ter(td.annualised, ter)),
                )
            )  # fmt: skip
        if tracking:
            columns = (
                self.t("isin"), self.t("period"), self.t("series_type"), self.t("td_period"),
                self.t("td_annualised"), self.t("ter"), self.t("td_plus_ter"),
            )  # fmt: skip
            align = ("left", "left", "left", "right", "right", "right", "right")
            notes = (self.t("td_note"),)
            tables.append(Table(self.t("lt_tracking"), columns, tuple(tracking), align, notes))
        return Section(self.t("lookthrough"), tuple(paragraphs), tuple(tables), ())

    def _exposure_table(self, dimension: Dimension, key: str) -> Table:
        assert self.lookthrough is not None
        exposures = self.lookthrough.exposures
        series = exposures.exposure(dimension)
        regular = [k for k in series.index if k not in SPECIAL_BUCKETS][:TOP_BUCKETS]
        special = [k for k in series.index if k in SPECIAL_BUCKETS]
        names = {}
        if dimension is Dimension.SECURITY:
            rows = exposures.rows.dropna(subset=["security"])
            names = dict(zip(rows["security"], rows["name"], strict=True))
        table_rows = tuple(
            (self._bucket_label(str(k), names), self.pct(float(series[k])))
            for k in regular + special
        )
        notes: tuple[str, ...] = ()
        hidden = len([k for k in series.index if k not in SPECIAL_BUCKETS]) - len(regular)
        if hidden > 0:
            notes = (self.t("lt_more", count=str(hidden)),)
        return Table(
            self.t(key), (self.t(key), self.t("weight")), table_rows, ("left", "right"), notes
        )

    def _bucket_label(self, key: str, names: Mapping[str, object]) -> str:
        special = {
            UNKNOWN: "bucket_unknown",
            UNEXPLAINED: "bucket_unexplained",
            NOT_LOOKED_THROUGH: "bucket_not_looked_through",
            CASH: "cash",
        }
        if key in special:
            return self.t(special[key])
        name = names.get(key)
        if isinstance(name, str) and not key.startswith("name:"):
            return f"{name} ({key})"
        return key.removeprefix("name:")

    def _name(self, isin: Isin) -> str:
        instrument = self.instruments.get(isin)
        return instrument.name if instrument else isin.code

    def _health_checks(self) -> Section:
        if self.checks is None:
            return Section(self.t("health_checks"), (self.t("checks_not_run"),), (), ())
        result = self.checks
        counts = {s: sum(f.severity is s for f in result.findings) for s in Severity}
        paragraphs = [
            self.t(
                "checks_summary",
                critical=str(counts[Severity.CRITICAL]),
                warning=str(counts[Severity.WARNING]),
                info=str(counts[Severity.INFO]),
                passed=str(len(result.passed)),
                not_applicable=str(len(result.not_applicable)),
                disabled=str(len(result.disabled)),
            ),
            self.t("checks_note"),
        ]
        if result.disabled:
            names = ", ".join(check_label(c, self.language)[0] for c in result.disabled)
            paragraphs.append(self.t("checks_disabled", checks=names))
        tables = []
        if result.findings:
            order = (Severity.CRITICAL, Severity.WARNING, Severity.INFO)
            ranked = sorted(result.findings, key=lambda f: order.index(f.severity))
            rows = tuple(
                (
                    self.t(f"severity_{f.severity.value}"),
                    check_label(f.check_id, self.language)[0],
                    self.t("subject_portfolio") if f.subject == "portfolio" else f.subject,
                    self._measure(f.observed, f.unit),
                    self._threshold(f),
                    "; ".join(
                        f"{detail_key(k, self.language)}: {detail_value(v, self.language)}"
                        for k, v in f.details.items()
                        if v
                    ),
                )
                for f in ranked
            )
            finding_columns = (
                self.t("severity"), self.t("check"), self.t("subject"), self.t("observed"),
                self.t("threshold"), self.t("details"),
            )  # fmt: skip
            align = ("left", "left", "left", "right", "right", "left")
            tables.append(Table(self.t("findings"), finding_columns, rows, align, ()))
        if result.not_applicable:
            reasons = tuple(
                (check_label(c, self.language)[0], translate(reason, self.language))
                for c, reason in result.not_applicable
            )
            untranslated = self.language is Language.EN or not all(
                is_known(reason) for _, reason in result.not_applicable
            )
            tables.append(
                Table(
                    self.t("checks_not_applicable"),
                    (self.t("check"), self.t("reason")),
                    reasons,
                    ("left", "left"),
                    (self.t("reasons_in_english"),) if untranslated else (),
                )
            )
        evaluated = (
            {f.check_id for f in result.findings}
            | set(result.passed)
            | {c for c, _ in result.not_applicable}
        )
        explained = tuple(
            check_label(spec.id, self.language) for spec in ALL_CHECKS if spec.id in evaluated
        )
        if explained:
            tables.append(
                Table(
                    self.t("checks_explained"),
                    (self.t("check"), self.t("explanation")),
                    explained,
                    ("left", "left"),
                    (),
                )
            )
        return Section(self.t("health_checks"), tuple(paragraphs), tuple(tables), ())

    def _measure(self, value: float, unit: MeasureUnit) -> str:
        if unit is MeasureUnit.FRACTION:
            return self.pct(value)
        if unit is MeasureUnit.MONEY:
            return self.money(Decimal(str(value)))
        if unit is MeasureUnit.COUNT:
            return format_number(value, 0, style=self.style)
        if unit is MeasureUnit.YEARS:
            return format_number(value, 1, style=self.style)
        return format_number(value, 2, style=self.style)

    def _threshold(self, finding: Finding) -> str:
        sign = ">" if finding.direction is Direction.ABOVE else "<"
        return f"{sign} {self._measure(finding.threshold, finding.unit)}"

    def _collect_warnings(self, twr: TwrResult, mwr: XirrResult | None) -> None:
        if self.checks is not None:
            critical = sum(f.severity is Severity.CRITICAL for f in self.checks.findings)
            if critical:
                self.warnings.append(self.t("warn_critical_findings", count=str(critical)))
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
