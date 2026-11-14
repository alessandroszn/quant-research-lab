"""Experiment kind ``portfolio_report``: broker export + prices + master data -> HTML report.

Inputs: ``transactions`` (broker export), ``transactions_mapping`` (TOML, phase 2.1),
``prices`` (price CSV), ``prices_mapping`` (TOML, phase 1.2; instrument ids must be ISINs),
``instruments`` (TOML, phase 1.3) and ``checks`` (TOML, phase 2.4).

Parameters (required): ``title``, ``base_currency``, ``language`` (``it``/``en``),
``flow_timing`` (``start``/``end``), ``max_price_age_days``, ``return_frequency``
(``monthly``/``none``), ``generated_at`` (date-time with time zone) and ``target_weights`` (a
table, possibly empty).

Several currencies (phase 7.4a), all optional:

- ``fx``: the ECB ``eurofxref-hist`` zip. Its provenance comes from the raw store's sidecar when
  there is one (checked against the file's SHA-256). With it, every amount and price is
  converted to ``base_currency`` with the ECB reference rate of its date, through EUR for a
  non-EUR base, and the report lists every rate carried forward. Without it, every amount and
  price must be in ``base_currency``.
- ``fx_max_age_days``: oldest acceptable rate in calendar days; required with ``fx`` and
  refused without it.
- ``[inputs.extra_prices]`` and ``[inputs.extra_prices_mapping]``: one more price file and its
  mapping per key (e.g. ``usd``), with the same keys in both groups, for prices in other
  currencies. An ISIN in two price files raises.

Valuation dates are the dates of all price files from the first transaction on. The report is
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
from qrlab.data.ecb import FX_DATASET, parse_ecb_fx
from qrlab.data.ecb import SOURCE as ECB_SOURCE
from qrlab.data.ecb import TERMS as ECB_TERMS
from qrlab.data.provenance import Provenance
from qrlab.data.user_csv import load_csv_mapping, parse_price_csv
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import (
    choice,
    local_provenance,
    moment,
    text,
    whole,
)
from qrlab.experiments.kinds._studies import raw_provenance
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.io import load_instruments
from qrlab.portfolio.broker_import import load_broker_mapping, parse_broker_csv
from qrlab.portfolio.ledger import ToBase, replay
from qrlab.portfolio.performance import FlowTiming, external_flows_by_date, time_weighted_returns
from qrlab.portfolio.valuation import EcbConverter, PriceSeries, value_portfolio
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
_OPTIONAL_INPUTS = ("fx",)
_GROUPS = ("extra_prices", "extra_prices_mapping")
_OPTIONAL_PARAMETERS = ("fx_max_age_days",)


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
    fx_max_age_days: int | None


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(
        parameters,
        required=set(_PARAMETERS),
        optional=set(_OPTIONAL_PARAMETERS),
        where="[parameters]",
    )
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
        fx_max_age_days=whole(parameters, "fx_max_age_days", minimum=0)
        if "fx_max_age_days" in parameters
        else None,
    )


def _check_inputs(parameters: object, names: frozenset[str]) -> None:
    p: _Parameters = parameters  # type: ignore[assignment]
    if ("fx" in names) != (p.fx_max_age_days is not None):
        raise ValidationError(
            "fx_max_age_days is required with an fx input and refused without one"
        )
    keys = [{n.split(".", 1)[1] for n in names if n.startswith(f"{g}.")} for g in _GROUPS]
    if keys[0] != keys[1]:
        raise ValidationError(
            "extra_prices and extra_prices_mapping need the same keys: "
            f"{sorted(keys[0])} and {sorted(keys[1])}"
        )


def _converter(context: RunContext, p: _Parameters) -> tuple[ToBase, str, list[Provenance]]:
    """Return the base-currency converter, its report description and its provenance."""
    if "fx" not in context.inputs:

        def base_only(amount: Money, on: date) -> Money:
            if amount.currency != p.base:
                raise CurrencyError(
                    f"{amount.currency.code} amount in a {p.base.code} portfolio: this "
                    "experiment kind is single-currency without an fx input (ECB reference "
                    "rates); give one to convert"
                )
            return amount

        return base_only, f"{p.base.code} only (no conversion)", []
    path = context.inputs["fx"]
    provenance = raw_provenance(path, source=ECB_SOURCE, dataset=FX_DATASET, terms=ECB_TERMS)
    age = p.fx_max_age_days
    assert age is not None  # checked at validation
    converter = EcbConverter(
        parse_ecb_fx(path.read_bytes(), provenance), base=p.base, max_age_days=age
    )
    return converter, f"ECB reference rates, max age {age} days", [provenance]


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    files = context.inputs
    to_base, fx_description, fx_provenance = _converter(context, p)
    export = files["transactions"]
    imported = parse_broker_csv(
        export.read_bytes(),
        local_provenance(export, dataset="transactions"),
        load_broker_mapping(files["transactions_mapping"]),
    )
    history = replay(imported.transactions, base=p.base, to_base=to_base)
    price_files = [("prices", files["prices"], files["prices_mapping"])]
    mappings = context.group("extra_prices_mapping")
    price_files += [
        (f"prices_{key}", path, mappings[key])
        for key, path in sorted(context.group("extra_prices").items())
    ]
    prices: dict[Isin, PriceSeries] = {}
    price_provenance: list[Provenance] = []
    price_dates: set[date] = set()
    for dataset, price_file, mapping in price_files:
        provenance = local_provenance(price_file, dataset=dataset)
        data = parse_price_csv(price_file.read_bytes(), provenance, load_csv_mapping(mapping))
        for column in data.dataset.data.columns:
            isin = Isin(column)
            if isin in prices:
                raise ValidationError(f"{isin.code} is in two price files")
            prices[isin] = PriceSeries.from_price_data(data, column)
        price_provenance.append(provenance)
        price_dates |= {d.date() for d in data.dataset.data.index}
    first = min(t.trade_date for t in imported.transactions)
    dates = sorted(d for d in price_dates if d >= first)
    if not dates:
        raise ValidationError("no price dates on or after the first transaction")
    valuation = value_portfolio(
        history, prices, to_base, dates=dates, max_price_age_days=p.max_price_age_days
    )
    instruments = {i.isin: i for i in load_instruments(files["instruments"])}
    twr = time_weighted_returns(valuation, external_flows_by_date(history), flow_timing=p.timing)
    check_context = CheckContext(
        as_of=dates[-1],
        history=history,
        valuation=valuation,
        to_base=to_base,
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
        to_base=to_base,
        language=p.language,
        generated_at=p.generated_at,
        flow_timing=p.timing,
        max_price_age_days=p.max_price_age_days,
        fx_description=fx_description,
        provenance=[imported.provenance, *price_provenance, *fx_provenance],
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
    optional_inputs=_OPTIONAL_INPUTS,
    input_groups=_GROUPS,
    optional_parameters=_OPTIONAL_PARAMETERS,
    check_inputs=_check_inputs,
)
