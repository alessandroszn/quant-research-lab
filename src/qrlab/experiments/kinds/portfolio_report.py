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

Look-through and tracking (phase 7.4b), all optional, keyed by fund ISIN:

- ``[inputs.holdings]`` and ``[inputs.holdings_mapping]``: the fund's holdings file and its
  mapping (phase 1.3), with ``[parameters.holdings.<ISIN>]`` giving ``as_of`` (the holdings
  date), ``weight_basis`` and ``sector_taxonomy`` (text, or ``"none"``). ``lookthrough_treatment``
  (``as_reported``/``normalised``) is required with holdings and refused without them. A fund
  not held on the last valuation date, or holdings dated after it, raise.
- ``issuers`` (phase 8.2): a CSV ``isin,issuer`` (:func:`qrlab.instruments.load_issuer_map`)
  that groups the securities of one issuer in the issuer exposure and its check; only with
  holdings files. Holdings may be CSV or xlsx, with country codes or names, as their mapping
  declares (:func:`qrlab.instruments.parse_holdings_file`).
- ``[inputs.tracking]`` and ``[inputs.tracking_mapping]``: a price file with exactly two
  columns, the fund's (instrument id = its ISIN; NAV or total return) and its index's (total
  return), with ``[parameters.tracking.<ISIN>]`` giving ``index_hedged_to`` (a currency code or
  ``"none"``). The fund's hedge currency comes from the instruments file.

With either, the look-through on the last valuation date goes to the health checks and the
report, and the run writes ``exposures.csv`` (one row per piece of exposure) and the scalars
``lookthrough_funds`` and ``unexplained_weight``. Without them, nothing changes.

Risk and stress tests (phase 8.3), optional: ``[parameters.risk]`` with ``frequency``
(``weekly``/``monthly``), ``window`` (number of returns), ``confidence`` and ``covariance`` (as in
``risk_report``), and an optional ``scenarios`` input (the TOML of ``scenario_analysis``). The
returns come from the report's own price files and the ECB rates of ``fx``, at today's weights;
see ``qrlab.experiments.kinds._portfolio_risk``. The run then writes ``risk_returns.csv``,
``risk_contributions.csv``, ``var_es.csv`` (and ``scenarios.csv``) and the scalars
``volatility_period``, ``volatility_annual``, ``var_historical`` and ``es_historical``.

Projection (phase 8.4), optional: ``[parameters.projection]`` projects today's portfolio
(value, weights, date) with stated return assumptions, one table per held position and one for
cash, a correlation for every pair of risky assets, flows (a savings plan), costs (a number or
``"ter"``, the weighted TER of the instruments file), inflation and taxes, and its own ``seed``.
The sensitivity table is always computed. See
``qrlab.experiments.kinds._portfolio_projection``. The run then writes ``fan_real.csv``,
``terminal.csv``, ``sensitivity.csv`` and the fan chart, and the projection scalars.

Valuation dates are the dates of all price files from the first transaction on. The report is
descriptive.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
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
from qrlab.data.provenance import Dataset, Provenance
from qrlab.data.user_csv import load_csv_mapping, parse_price_csv
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._frames import ADVICE
from qrlab.experiments.kinds._params import (
    choice,
    day,
    local_provenance,
    moment,
    text,
    whole,
)
from qrlab.experiments.kinds._portfolio_projection import (
    ProjectionSpec,
    parse_projection,
    project_portfolio,
)
from qrlab.experiments.kinds._portfolio_risk import PRICE_ONLY, RiskSpec, compute_risk, parse_risk
from qrlab.experiments.kinds._studies import raw_provenance
from qrlab.experiments.kinds.projection import SCENARIOS
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.io import (
    load_holdings_mapping,
    load_instruments,
    load_issuer_map,
    parse_holdings_file,
)
from qrlab.instruments.master import Instrument
from qrlab.lookthrough.exposures import UNEXPLAINED, WeightTreatment, look_through
from qrlab.lookthrough.inputs import LookThroughInputs
from qrlab.lookthrough.tracking import TrackingSeries, tracking_difference
from qrlab.portfolio.broker_import import load_broker_mapping, parse_broker_csv
from qrlab.portfolio.ledger import ToBase, replay
from qrlab.portfolio.performance import FlowTiming, external_flows_by_date, time_weighted_returns
from qrlab.portfolio.valuation import EcbConverter, PriceSeries, value_portfolio
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import render_html
from qrlab.reporting.portfolio_report import build_portfolio_report
from qrlab.scenarios.definitions import load_scenarios

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
_OPTIONAL_INPUTS = ("fx", "issuers", "scenarios")
_GROUPS = (
    "extra_prices",
    "extra_prices_mapping",
    "holdings",
    "holdings_mapping",
    "tracking",
    "tracking_mapping",
)
_OPTIONAL_PARAMETERS = (
    "fx_max_age_days",
    "lookthrough_treatment",
    "holdings",
    "tracking",
    "risk",
    "projection",
)


@dataclass(frozen=True)
class _Holdings:
    as_of: date
    weight_basis: str
    sector_taxonomy: str | None


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
    risk: RiskSpec | None
    projection: ProjectionSpec | None
    treatment: WeightTreatment | None
    holdings: Mapping[Isin, _Holdings]
    index_hedged_to: Mapping[Isin, Currency | None]


def _per_fund(
    parameters: Mapping[str, object], key: str, required: set[str]
) -> dict[Isin, Mapping[str, object]]:
    """Read ``[parameters.<key>.<ISIN>]`` tables (absent: empty)."""
    if key not in parameters:
        return {}
    value = parameters[key]
    if not isinstance(value, dict) or not value:
        raise ValidationError(f"[parameters.{key}] must hold one table per fund ISIN")
    out: dict[Isin, Mapping[str, object]] = {}
    for code, spec in value.items():
        if not isinstance(spec, dict):
            raise ValidationError(f"[parameters.{key}.{code}] must be a table")
        require_keys(spec, required=required, optional=set(), where=f"[parameters.{key}.{code}]")
        out[Isin(code)] = spec
    return out


def _currency_or_none(parent: Mapping[str, object], key: str) -> Currency | None:
    value = text(parent, key)
    return None if value == "none" else Currency(value)


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
        risk=parse_risk(parameters),
        projection=parse_projection(parameters),
        treatment=WeightTreatment(
            choice(parameters, "lookthrough_treatment", {"as_reported", "normalised"})
        )
        if "lookthrough_treatment" in parameters
        else None,
        holdings={
            isin: _Holdings(
                as_of=day(spec, "as_of"),
                weight_basis=text(spec, "weight_basis"),
                sector_taxonomy=None
                if text(spec, "sector_taxonomy") == "none"
                else text(spec, "sector_taxonomy"),
            )
            for isin, spec in _per_fund(
                parameters, "holdings", {"as_of", "weight_basis", "sector_taxonomy"}
            ).items()
        },
        index_hedged_to={
            isin: _currency_or_none(spec, "index_hedged_to")
            for isin, spec in _per_fund(parameters, "tracking", {"index_hedged_to"}).items()
        },
    )


def _check_inputs(parameters: object, names: frozenset[str]) -> None:
    p: _Parameters = parameters  # type: ignore[assignment]
    if ("fx" in names) != (p.fx_max_age_days is not None):
        raise ValidationError(
            "fx_max_age_days is required with an fx input and refused without one"
        )

    def keys(group: str) -> set[str]:
        return {n.split(".", 1)[1] for n in names if n.startswith(f"{group}.")}

    pairs: list[tuple[str, set[str], set[str], set[str] | None]] = [
        ("extra_prices and extra_prices_mapping", keys("extra_prices"),
         keys("extra_prices_mapping"), None),
        ("holdings, holdings_mapping and [parameters.holdings]", keys("holdings"),
         keys("holdings_mapping"), {i.code for i in p.holdings}),
        ("tracking, tracking_mapping and [parameters.tracking]", keys("tracking"),
         keys("tracking_mapping"), {i.code for i in p.index_hedged_to}),
    ]  # fmt: skip
    for label, files, file_mappings, specs in pairs:
        if files != file_mappings or (specs is not None and specs != files):
            given = [sorted(files), sorted(file_mappings)] + ([sorted(specs)] if specs else [])
            raise ValidationError(f"{label} need the same keys: got {given}")
    if bool(keys("holdings")) != (p.treatment is not None):
        raise ValidationError(
            "lookthrough_treatment is required with holdings and refused without them"
        )
    if "scenarios" in names and p.risk is None:
        raise ValidationError("a scenarios file is used only with [parameters.risk]")
    if "issuers" in names and not keys("holdings"):
        raise ValidationError("an issuers file is used only with holdings files")


def _converter(
    context: RunContext, p: _Parameters
) -> tuple[ToBase, str, list[Provenance], Dataset | None]:
    """Return the converter, its report description, its provenance and the FX dataset."""
    if "fx" not in context.inputs:

        def base_only(amount: Money, on: date) -> Money:
            if amount.currency != p.base:
                raise CurrencyError(
                    f"{amount.currency.code} amount in a {p.base.code} portfolio: this "
                    "experiment kind is single-currency without an fx input (ECB reference "
                    "rates); give one to convert"
                )
            return amount

        return base_only, f"{p.base.code} only (no conversion)", [], None
    path = context.inputs["fx"]
    provenance = raw_provenance(path, source=ECB_SOURCE, dataset=FX_DATASET, terms=ECB_TERMS)
    age = p.fx_max_age_days
    assert age is not None  # checked at validation
    rates = parse_ecb_fx(path.read_bytes(), provenance)
    converter = EcbConverter(rates, base=p.base, max_age_days=age)
    return converter, f"ECB reference rates, max age {age} days", [provenance], rates


def _lookthrough(
    context: RunContext,
    p: _Parameters,
    check_context: CheckContext,
    instruments: Mapping[Isin, Instrument],
) -> tuple[LookThroughInputs | None, list[Provenance]]:
    """Build the look-through on the last valuation date from the holdings and tracking files."""
    holdings_files, tracking_files = context.group("holdings"), context.group("tracking")
    if not holdings_files and not tracking_files:
        return None, []
    as_of = check_context.as_of
    weights = check_context.position_weights()
    provenance: list[Provenance] = []

    def held(code: str, what: str) -> Isin:
        isin = Isin(code)
        if isin not in weights:
            raise ValidationError(f"{what} of {code}: the fund is not held on {as_of}")
        return isin

    snapshots = {}
    mappings = context.group("holdings_mapping")
    for code, path in sorted(holdings_files.items()):
        isin = held(code, "holdings")
        spec = p.holdings[isin]
        source = local_provenance(path, dataset=f"holdings_{code}")
        snapshots[isin] = parse_holdings_file(
            path.read_bytes(),
            source,
            load_holdings_mapping(mappings[code]),
            fund=isin,
            as_of=spec.as_of,
            weight_basis=spec.weight_basis,
            sector_taxonomy=spec.sector_taxonomy,
        )
        provenance.append(source)
    tracking = {}
    mappings = context.group("tracking_mapping")
    for code, path in sorted(tracking_files.items()):
        isin = held(code, "tracking")
        source = local_provenance(path, dataset=f"tracking_{code}")
        data = parse_price_csv(path.read_bytes(), source, load_csv_mapping(mappings[code]))
        columns = [str(c) for c in data.dataset.data.columns]
        if code not in columns or len(columns) != 2:
            raise ValidationError(
                f"tracking file of {code} needs exactly two columns: the column for {code} (the "
                f"fund) and one for its index; got {columns}"
            )
        if isin not in instruments:
            raise ValidationError(f"tracking of {code}: the fund is not in the instruments file")
        index_column = next(c for c in columns if c != code)
        currency = data.dataset.currency
        assert currency is not None  # a price mapping always has a currency
        fund = TrackingSeries(
            data.dataset.data[code], data.price_types[code], currency, instruments[isin].hedged_to
        )
        index = TrackingSeries(
            data.dataset.data[index_column],
            data.price_types[index_column],
            currency,
            p.index_hedged_to[isin],
        )
        tracking_difference(fund, index)  # refuses series that cannot be compared
        tracking[isin] = (fund, index)
        provenance.append(source)
    issuers = None
    if "issuers" in context.inputs:
        issuers = load_issuer_map(context.inputs["issuers"])
        provenance.append(local_provenance(context.inputs["issuers"], dataset="issuers"))
    exposures = look_through(
        as_of=as_of,
        position_weights=weights,
        cash_weights=check_context.cash_weights(),
        instruments=instruments,
        snapshots=snapshots,
        treatment=p.treatment or WeightTreatment.AS_REPORTED,  # no holdings: nothing to weigh
        issuers=issuers,
    )
    return LookThroughInputs(exposures, snapshots, tracking), provenance


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    files = context.inputs
    to_base, fx_description, fx_provenance, fx_rates = _converter(context, p)
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
    lookthrough, lookthrough_provenance = _lookthrough(context, p, check_context, instruments)
    check_context = replace(check_context, lookthrough=lookthrough)
    checks = run_checks(check_context, load_check_config(files["checks"]))
    risk = None
    if p.risk is not None:
        position_weights = check_context.position_weights()
        risk = compute_risk(
            p.risk,
            as_of=dates[-1],
            value=float(valuation.totals[dates[-1]]),
            base=p.base,
            prices=prices,
            names={isin: instrument.name for isin, instrument in instruments.items()},
            position_weights=position_weights,
            cash_weights=check_context.cash_weights(),
            exposure_currencies={i: check_context.exposure_currency(i) for i in position_weights},
            fx=fx_rates,
            scenarios=load_scenarios(files["scenarios"]) if "scenarios" in files else (),
        )
    plan = None
    if p.projection is not None:
        plan = project_portfolio(
            p.projection,
            start=dates[-1],
            value=float(valuation.totals[dates[-1]]),
            base=p.base,
            position_weights=check_context.position_weights(),
            cash_weight=sum(check_context.cash_weights().values()),
            instruments=instruments,
        )
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
        provenance=[
            imported.provenance,
            *price_provenance,
            *lookthrough_provenance,
            *fx_provenance,
        ],
        instruments=instruments,
        import_notes=list(imported.notes),
        return_frequency=(Frequency.MONTHLY, 12.0) if p.monthly else None,
        checks=checks,
        lookthrough=lookthrough,
        risk=None if risk is None else risk.summary,
        projection=None if plan is None else plan[0].result,
    )
    findings = pd.DataFrame(
        [
            (f.check_id, f.severity.value, f.subject, f.observed, f.threshold)
            for f in checks.findings
        ],
        columns=["check", "severity", "subject", "observed", "threshold"],
    )
    end = valuation.totals[dates[-1]]
    tables = {"check_findings": Tagged(findings, "descriptive")}
    scalars = {
        "end_value": Tagged(float(end), "descriptive"),
        "twr_total": Tagged(float(twr.total), "descriptive"),
        "critical_findings": Tagged(
            float(sum(f.severity.value == "critical" for f in checks.findings)), "descriptive"
        ),
    }
    if lookthrough is not None:
        rows = lookthrough.exposures.rows
        tables["exposures"] = Tagged(rows.rename_axis("row"), "descriptive")
        scalars["lookthrough_funds"] = Tagged(float(len(lookthrough.snapshots)), "descriptive")
        scalars["unexplained_weight"] = Tagged(
            float(rows.loc[rows["kind"] == UNEXPLAINED, "weight"].sum()), "descriptive"
        )
    caveats = []
    figures = {}
    if risk is not None:
        tables |= risk.tables
        scalars |= risk.scalars
        if risk.price_only:
            caveats.append(PRICE_ONLY.format(names=", ".join(risk.price_only)))
    if plan is not None:
        run, cost = plan
        summary = run.result.summary
        tables |= run.tables
        figures["fan_real"] = run.figure
        scalars |= {
            "projection_p_goal": Tagged(summary.p_goal, "descriptive"),
            "projection_p_goal_se": Tagged(summary.p_goal_se, "descriptive"),
            "projection_terminal_mean_real": Tagged(summary.terminal_mean_real, "descriptive"),
            "projection_annual_cost": Tagged(cost, "descriptive"),
        }
        caveats.append(SCENARIOS)
    return ExperimentOutput(
        tables=tables,
        scalars=scalars,
        figures=figures,
        report_html=render_html(report),
        notice=" ".join([*caveats, ADVICE]) if caveats else None,
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
