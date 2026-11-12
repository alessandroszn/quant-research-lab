"""Experiment kind ``portfolio_report``: broker export + prices + master data -> HTML report.

Inputs: ``transactions`` (broker export), ``transactions_mapping`` (TOML, phase 2.1),
``prices`` (price CSV), ``prices_mapping`` (TOML, phase 1.2; instrument ids must be ISINs),
``instruments`` (TOML, phase 1.3) and ``checks`` (TOML, phase 2.4).

Parameters (all required): ``title``, ``base_currency`` (single-currency portfolios in this
version: every amount and price must be in it), ``language`` (``it``/``en``), ``flow_timing``
(``start``/``end``), ``max_price_age_days``, ``return_frequency`` (``monthly``/``none``),
``generated_at`` (date-time with time zone) and ``target_weights`` (a table, possibly empty).
Valuation dates are the price-file dates from the first transaction on. The report is
descriptive.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from qrlab.checks.context import CheckContext
from qrlab.checks.engine import load_check_config, run_checks
from qrlab.core.calendar import Frequency
from qrlab.core.errors import CurrencyError, ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.user_csv import load_csv_mapping, parse_price_csv
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import (
    choice,
    local_provenance,
    moment,
    text,
    whole,
)
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.io import load_instruments
from qrlab.portfolio.broker_import import load_broker_mapping, parse_broker_csv
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.performance import FlowTiming, external_flows_by_date, time_weighted_returns
from qrlab.portfolio.valuation import PriceSeries, value_portfolio
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import render_html
from qrlab.reporting.portfolio_report import build_portfolio_report

__all__ = ["KIND"]

_PARAMETERS = (
    "title",
    "base_currency",
    "language",
    "flow_timing",
    "max_price_age_days",
    "return_frequency",
    "generated_at",
    "target_weights",
)
_INPUTS = (
    "transactions",
    "transactions_mapping",
    "prices",
    "prices_mapping",
    "instruments",
    "checks",
)


@dataclass(frozen=True)
class _Parameters:
    title: str
    base: Currency
    language: Language
    timing: FlowTiming
    max_price_age_days: int
    monthly: bool
    generated_at: datetime
    targets: Mapping[str, float] | None


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    targets = parameters["target_weights"]
    if not isinstance(targets, dict) or not all(type(v) in (int, float) for v in targets.values()):
        raise ValidationError("target_weights must be a table of numbers (empty for none)")
    return _Parameters(
        title=text(parameters, "title"),
        base=Currency(text(parameters, "base_currency")),
        language=Language(choice(parameters, "language", {"it", "en"})),
        timing=FlowTiming.START_OF_DAY
        if choice(parameters, "flow_timing", {"start", "end"}) == "start"
        else FlowTiming.END_OF_DAY,
        max_price_age_days=whole(parameters, "max_price_age_days", minimum=0),
        monthly=choice(parameters, "return_frequency", {"monthly", "none"}) == "monthly",
        generated_at=moment(parameters, "generated_at"),
        targets={str(k): float(v) for k, v in targets.items()} or None,
    )


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    files = context.inputs

    def base_only(amount: Money, on: date) -> Money:
        if amount.currency != p.base:
            raise CurrencyError(
                f"{amount.currency.code} amount in a {p.base.code} portfolio: this experiment "
                "kind supports single-currency portfolios only"
            )
        return amount

    export = files["transactions"]
    imported = parse_broker_csv(
        export.read_bytes(),
        local_provenance(export, dataset="transactions"),
        load_broker_mapping(files["transactions_mapping"]),
    )
    history = replay(imported.transactions, base=p.base, to_base=base_only)
    price_file = files["prices"]
    price_provenance = local_provenance(price_file, dataset="prices")
    data = parse_price_csv(
        price_file.read_bytes(), price_provenance, load_csv_mapping(files["prices_mapping"])
    )
    prices = {
        Isin(column): PriceSeries.from_price_data(data, column)
        for column in data.dataset.data.columns
    }
    first = min(t.trade_date for t in imported.transactions)
    dates = [d.date() for d in data.dataset.data.index if d.date() >= first]
    if not dates:
        raise ValidationError("no price dates on or after the first transaction")
    valuation = value_portfolio(
        history, prices, base_only, dates=dates, max_price_age_days=p.max_price_age_days
    )
    instruments = {i.isin: i for i in load_instruments(files["instruments"])}
    twr = time_weighted_returns(valuation, external_flows_by_date(history), flow_timing=p.timing)
    check_context = CheckContext(
        as_of=dates[-1],
        history=history,
        valuation=valuation,
        to_base=base_only,
        instruments=instruments,
        prices=prices,
        portfolio_returns=twr.returns,
        benchmark_returns=None,
        target_weights=p.targets,
        lookthrough=None,
    )
    checks = run_checks(check_context, load_check_config(files["checks"]))
    report = build_portfolio_report(
        name=p.title,
        history=history,
        valuation=valuation,
        prices=prices,
        to_base=base_only,
        language=p.language,
        generated_at=p.generated_at,
        flow_timing=p.timing,
        max_price_age_days=p.max_price_age_days,
        fx_description=f"{p.base.code} only (no conversion)",
        provenance=[imported.provenance, price_provenance],
        instruments=instruments,
        import_notes=list(imported.notes),
        return_frequency=(Frequency.MONTHLY, 12.0) if p.monthly else None,
        checks=checks,
        lookthrough=None,
        risk=None,
        projection=None,
    )
    findings = pd.DataFrame(
        [
            (f.check_id, f.severity.value, f.subject, f.observed, f.threshold)
            for f in checks.findings
        ],
        columns=["check", "severity", "subject", "observed", "threshold"],
    )
    end = valuation.totals[dates[-1]]
    return ExperimentOutput(
        tables={"check_findings": Tagged(findings, "descriptive")},
        scalars={
            "end_value": Tagged(float(end), "descriptive"),
            "twr_total": Tagged(float(twr.total), "descriptive"),
            "critical_findings": Tagged(
                float(sum(f.severity.value == "critical" for f in checks.findings)), "descriptive"
            ),
        },
        report_html=render_html(report),
    )


KIND = ExperimentKind(
    name="portfolio_report",
    description="HTML portfolio report with health checks from a broker export (descriptive)",
    inputs=_INPUTS,
    needs_seed=False,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
)
