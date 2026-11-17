"""Experiment kind ``portfolio_report``: broker export + prices + master data -> HTML report.

Inputs: ``transactions``, ``prices`` (price CSV), ``prices_mapping`` (TOML, phase 1.2;
instrument ids must be ISINs), ``instruments`` (TOML, phase 1.3) and ``checks`` (TOML, phase
2.4). How ``transactions`` is read is the required parameter ``transactions_format`` (phase
8.8): ``"mapped"``, a broker export read with the ``transactions_mapping`` input (TOML, phase
2.1); ``"native"``, a native qrlab transactions file (:mod:`qrlab.portfolio.native`), with no
mapping.

Parameters (required): ``transactions_format``, ``title``, ``base_currency``, ``language``
(``it``/``en``),
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
Optional in ``[parameters.risk]`` (phase 11.4): ``[parameters.risk.backtest]`` (``window``,
``model``: ``historical``, ``normal`` or ``cornish_fisher``) backtests the VaR model on today's
weights over the common history (Kupiec, Christoffersen), writing ``var_backtest.csv`` and its
scalars (``out_of_sample``); ``[parameters.risk.proxies]`` (ISIN = { factor = beta }) with the
``factors`` and ``factors_mapping`` inputs (total-return factor levels in the proxied
positions' exposure currency) maps positions without their own history to the factors in the
stress tests.

Projection (phase 8.4), optional: ``[parameters.projection]`` projects today's portfolio
(value, weights, date) with stated return assumptions, one table per held position and one for
cash, a correlation for every pair of risky assets, flows (a savings plan), costs (a number or
``"ter"``, the weighted TER of the instruments file), inflation and taxes, and its own ``seed``.
The sensitivity table is always computed. See
``qrlab.experiments.kinds._portfolio_projection``. The run then writes ``fan_real.csv``,
``terminal.csv``, ``sensitivity.csv`` and the fan chart, and the projection scalars.

Risk-free rate (phase 8.5), optional: an ``estr`` input, the ECB Data Portal file of the euro
short-term rate (provenance from the raw store's sidecar). It needs ``return_frequency =
"monthly"``. Each TWR period's risk-free return is the €STR compounded over exactly its dates
(:func:`qrlab.core.rates.overnight_returns`, ACT/360, TARGET calendar); the report then shows
the risk-free return and the Sharpe ratio of the excess returns, annualised by sqrt(12), with
its Mertens (2002) standard error and the number of returns. The run writes
``risk_free.csv`` and the scalars ``risk_free_total``, ``sharpe_ratio`` and
``sharpe_ratio_se``.

Tax position (phases 8.6a and 9.1), optional: ``[parameters.tax]`` with ``country`` (a code of
:data:`qrlab.tax.REGIMES`), then that country's own keys. The report gains a "Tax position
(analytics, not tax advice)" section, with its sources; the run writes the country's tables
and scalars (:class:`qrlab.tax.TaxReport`). Italy (``country = "it"``): ``regime``
(``amministrato``/``dichiarativo``) and ``public_share`` (a table: ISIN -> share of Italian and
white-list government bonds, required for every fund and bond sold; 0 for an equity fund);
it writes ``tax_events.csv``, ``losses_balance.csv`` and the scalars ``tax_due``,
``tax_withheld`` and ``losses_remaining``. See :mod:`qrlab.tax.italy`. Its optional
``custody`` (phase 11.3) says where each account is held: ``{ where = "italy", statements =
"year" | "quarter" | "month" }`` for the stamp duty, ``{ where = "abroad" |
"abroad_privileged", share }`` for the IVAFE; it adds ``wealth_tax_items.csv``,
``wealth_tax_years.csv`` and the scalars ``stamp_duty_last_year`` and ``ivafe_last_year``
(:mod:`qrlab.tax.italy_wealth`). Switzerland
(``country = "ch"``, phase 9.2, base currency CHF): ``marginal_rate``, ``wealth_tax_rate``,
``net_income`` (year = amount), ``debt_financed`` and ``reported_income`` (ISIN = list of
``{ date, per_unit, currency }`` from the ESTV price list); it writes ``ch_years.csv``,
``ch_safe_haven.csv`` and ``ch_income.csv``. See :mod:`qrlab.tax.switzerland`. The
configurable model (``country = "custom"``, phase 9.3, any base currency): ``description``,
``gains_rate``, ``income_rate``, ``losses`` (``ignored``/``netted``), ``loss_carry_years``,
``exempt_after_months``, ``gains_allowance`` and ``wealth_tax_rate``; it writes
``custom_years.csv`` and, with netted losses, ``custom_losses.csv``, and adds a sentence to
the notice. See :mod:`qrlab.tax.custom`.

The projection may add ``losses = { carry_years }`` (phase 11.5: the held ETFs and funds of
the instruments file are the fund assets) and ``income_tax_rate`` and ``taxable_yield`` (both
or neither, phase 9.2): a yearly tax of their product on value.

Income in the returns (design note 11.1), all optional. Risk and the diversification checks
read returns; valuation keeps the market prices. Per held position, by ISIN:

- ``total_returns`` and ``total_returns_mapping``: a price file whose columns are total-return
  series (``price_type = "total_return"``), each in the currency of the position's price file;
- ``[parameters.distributions]``: ISIN = list of ``{ ex_date, per_unit, currency }``, gross
  amounts per unit in the price file's currency, which adjust the position's prices
  (:func:`qrlab.core.returns.distribution_adjusted`).

Otherwise the price is used, which includes the income for a ``total_return`` price file, an
accumulating fund and an ETC. The notice names every other position, with the reason, when
risk or a diversification check reads returns; with risk the run writes
``return_sources.csv`` and the report shows the source of each position's returns.

Benchmark (design note 11.2), optional: ``benchmark`` and ``benchmark_mapping`` (a price file
with exactly one ``total_return`` column) with ``[parameters.benchmark]`` and its ``name``. On
each valuation date the benchmark is its last level (within ``max_price_age_days``) times the
ECB rate (within ``fx_max_age_days``). It is compared with the TWR on the periods between two
valuation dates: cumulative returns always; with ``return_frequency = "monthly"`` also the
tracking error, the information ratio and a CAPM regression (on excess returns over the €STR
with an ``estr`` input, else on returns). The run writes ``benchmark.csv`` and the scalars
``benchmark_total``, ``active_total``, ``tracking_error``, ``information_ratio``, ``beta``,
``beta_se``, ``alpha_annual``, ``alpha_annual_se`` and ``r_squared`` when they exist; the
checks then get both series on those periods, so ``risk.beta`` applies.

Valuation dates are the dates of all price files from the first transaction on. The report is
descriptive.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime

import numpy as np
import pandas as pd

from qrlab.checks.context import CheckContext
from qrlab.checks.engine import load_check_config, run_checks
from qrlab.core.calendar import Frequency, target2_calendar
from qrlab.core.errors import CurrencyError, ValidationError
from qrlab.core.money import Currency, Money
from qrlab.core.rates import overnight_returns
from qrlab.data.ecb import FX_DATASET, parse_ecb_fx, parse_estr
from qrlab.data.ecb import SOURCE as ECB_SOURCE
from qrlab.data.ecb import TERMS as ECB_TERMS
from qrlab.data.provenance import Dataset, Provenance
from qrlab.data.user_csv import PriceData, PriceType, load_csv_mapping, parse_price_csv
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
from qrlab.experiments.kinds._portfolio_benchmark import (
    BenchmarkOutputs,
    BenchmarkSpec,
    benchmark_series,
    compare,
    parse_benchmark,
)
from qrlab.experiments.kinds._portfolio_projection import (
    ProjectionSpec,
    parse_projection,
    project_portfolio,
)
from qrlab.experiments.kinds._portfolio_risk import RiskSpec, compute_risk, parse_risk
from qrlab.experiments.kinds._return_sources import (
    Payment,
    excluded_note,
    parse_distributions,
    return_levels,
)
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
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.performance import SharpeSE, sharpe_ratio
from qrlab.portfolio.broker_import import load_broker_mapping, parse_broker_csv
from qrlab.portfolio.ledger import ToBase, replay
from qrlab.portfolio.native import parse_native_csv
from qrlab.portfolio.performance import FlowTiming, external_flows_by_date, time_weighted_returns
from qrlab.portfolio.valuation import EcbConverter, PriceSeries, value_portfolio
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import render_html
from qrlab.reporting.portfolio_report import (
    ReturnSource,
    RiskFreeSummary,
    build_portfolio_report,
)
from qrlab.scenarios.definitions import load_scenarios
from qrlab.tax.regime import ColumnKind, TaxInputs, TaxRegime, TaxReport
from qrlab.tax.regimes import REGIMES, regime_for

__all__ = ["KIND"]

_PARAMETERS = (
    "transactions_format",
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
    "prices",
    "prices_mapping",
    "instruments",
    "checks",
)
_OPTIONAL_INPUTS = (
    "fx",
    "issuers",
    "scenarios",
    "estr",
    "transactions_mapping",
    "total_returns",
    "total_returns_mapping",
    "benchmark",
    "benchmark_mapping",
    "factors",
    "factors_mapping",
)
_FORMAT_HINT = (
    'transactions_format is required: "mapped" for a broker export read with '
    'transactions_mapping, "native" for a native qrlab transactions file (phase 8.8)'
)
DECLARED_COST = (
    "Some units were transferred in at a declared original cost: gains and taxes use that "
    "cost, performance is measured from the transfer at market value, and the gain carried in "
    "is shown apart in the profit and loss."
)
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
    "tax",
    "distributions",
    "benchmark",
)


@dataclass(frozen=True)
class _Holdings:
    as_of: date
    weight_basis: str
    sector_taxonomy: str | None


@dataclass(frozen=True)
class _Parameters:
    native: bool
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
    tax: tuple[TaxRegime, object] | None
    treatment: WeightTreatment | None
    holdings: Mapping[Isin, _Holdings]
    index_hedged_to: Mapping[Isin, Currency | None]
    distributions: Mapping[Isin, tuple[Payment, ...]]
    benchmark: BenchmarkSpec | None


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
    if "transactions_format" not in parameters:
        raise ValidationError(_FORMAT_HINT)
    require_keys(
        parameters,
        required=set(_PARAMETERS),
        optional=set(_OPTIONAL_PARAMETERS),
        where="[parameters]",
    )
    _check_tax_base(parameters)
    targets = parameters["target_weights"]
    if not isinstance(targets, dict) or not all(type(v) in (int, float) for v in targets.values()):
        raise ValidationError("target_weights must be a table of numbers (empty for none)")
    return _Parameters(
        native=choice(parameters, "transactions_format", {"native", "mapped"}) == "native",
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
        tax=_parse_tax(parameters),
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
        distributions=parse_distributions(parameters),
        benchmark=parse_benchmark(parameters),
    )


def _check_tax_base(parameters: Mapping[str, object]) -> None:
    """Refuse a base currency the chosen country cannot use (e.g. EUR with Swiss taxes)."""
    spec = parameters.get("tax")
    if not isinstance(spec, dict) or "country" not in spec:
        return
    needed = regime_for(spec["country"]).base_currency
    base = parameters["base_currency"]
    if needed is not None and base != needed.code:
        raise ValidationError(
            f'[parameters.tax] country = "{spec["country"]}" needs base_currency = '
            f'"{needed.code}", not {base!r}'
        )


def _parse_tax(parameters: Mapping[str, object]) -> tuple[TaxRegime, object] | None:
    """Read ``[parameters.tax]``: the country, then its own keys (phase 9.1), or ``None``."""
    if "tax" not in parameters:
        return None
    spec = parameters["tax"]
    if not isinstance(spec, dict):
        raise ValidationError("tax must be a table")
    if "country" not in spec:
        raise ValidationError(
            f"[parameters.tax] needs country, one of {sorted(REGIMES)} (phase 9.1)"
        )
    regime = regime_for(spec["country"])
    rest = {key: value for key, value in spec.items() if key != "country"}
    require_keys(rest, required=set(regime.keys), optional=set(regime.optional_keys), where="tax")
    return regime, regime.parse(rest)


def _check_inputs(parameters: object, names: frozenset[str]) -> None:
    p: _Parameters = parameters  # type: ignore[assignment]
    if p.native == ("transactions_mapping" in names):
        raise ValidationError(
            'transactions_format = "native" takes no transactions_mapping input'
            if p.native
            else 'transactions_format = "mapped" needs a transactions_mapping input'
        )
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
    if "estr" in names and not p.monthly:
        raise ValidationError(
            'an estr input needs return_frequency = "monthly": the Sharpe ratio is on monthly '
            "returns"
        )
    if "scenarios" in names and p.risk is None:
        raise ValidationError("a scenarios file is used only with [parameters.risk]")
    if "issuers" in names and not keys("holdings"):
        raise ValidationError("an issuers file is used only with holdings files")
    if ("total_returns" in names) != ("total_returns_mapping" in names):
        raise ValidationError("total_returns and total_returns_mapping go together")
    proxies = p.risk is not None and p.risk.proxies is not None
    if ("factors" in names) != ("factors_mapping" in names) or ("factors" in names) != proxies:
        raise ValidationError("factors, factors_mapping and [parameters.risk.proxies] go together")
    benchmark_parts = {"benchmark" in names, "benchmark_mapping" in names, p.benchmark is not None}
    if len(benchmark_parts) != 1:
        raise ValidationError("benchmark, benchmark_mapping and [parameters.benchmark] go together")


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


def _total_returns(context: RunContext) -> tuple[PriceData | None, list[Provenance]]:
    """Read the optional total-return series and its mapping (design note 11.1)."""
    if "total_returns" not in context.inputs:
        return None, []
    path = context.inputs["total_returns"]
    provenance = local_provenance(path, dataset="total_returns")
    mapping = load_csv_mapping(context.inputs["total_returns_mapping"])
    return parse_price_csv(path.read_bytes(), provenance, mapping), [provenance]


def _factor_returns(
    context: RunContext, check_context: CheckContext, spec: RiskSpec
) -> pd.DataFrame | None:
    """Read the factor levels for the stress-test proxies and return their returns (11.4)."""
    if "factors" not in context.inputs or spec.proxies is None:
        return None
    path = context.inputs["factors"]
    data = parse_price_csv(
        path.read_bytes(),
        local_provenance(path, dataset="factors"),
        load_csv_mapping(context.inputs["factors_mapping"]),
    )
    wrong = sorted(c for c, kind in data.price_types.items() if kind is not PriceType.TOTAL_RETURN)
    if wrong:
        raise ValidationError(
            f'factors: {wrong} must declare price_type = "total_return", like the positions\' '
            "returns"
        )
    currency = data.dataset.currency
    assert currency is not None  # a price mapping always has a currency
    for isin in sorted(spec.proxies, key=lambda i: i.code):
        if isin not in check_context.position_weights():
            continue  # compute_risk names proxies of positions not held
        exposure = check_context.exposure_currency(isin)
        if exposure != currency:
            raise ValidationError(
                f"factors are in {currency.code}, {isin.code} is exposed to {exposure.code}: "
                "a proxy maps factor returns in the position's exposure currency"
            )
    levels = data.dataset.data.astype("float64")
    return levels.pct_change(fill_method=None).iloc[1:]


def _benchmark(
    context: RunContext,
    p: _Parameters,
    dates: list[date],
    twr_returns: pd.Series,
    risk_free_table: pd.DataFrame | None,
    fx_rates: Dataset | None,
) -> tuple[BenchmarkOutputs | None, list[Provenance]]:
    """Compare the TWR with the optional benchmark (design note 11.2)."""
    if p.benchmark is None:
        return None, []
    path = context.inputs["benchmark"]
    provenance = local_provenance(path, dataset="benchmark")
    data = parse_price_csv(
        path.read_bytes(), provenance, load_csv_mapping(context.inputs["benchmark_mapping"])
    )
    level, currency = benchmark_series(data)
    outputs = compare(
        p.benchmark,
        level=level,
        currency=currency,
        base=p.base,
        fx=fx_rates,
        fx_max_age_days=p.fx_max_age_days,
        max_price_age_days=p.max_price_age_days,
        dates=dates,
        twr_returns=twr_returns,
        risk_free=None if risk_free_table is None else risk_free_table["risk_free"],
        monthly=p.monthly,
    )
    return outputs, [provenance]


def _risk_free(
    context: RunContext, dates: list[date], twr_returns: pd.Series
) -> tuple[RiskFreeSummary | None, pd.DataFrame | None, list[Provenance]]:
    """Return the €STR over the TWR periods, the Sharpe ratio, its table and provenance."""
    if "estr" not in context.inputs:
        return None, None, []
    path = context.inputs["estr"]
    provenance = raw_provenance(path, source=ECB_SOURCE, dataset="estr", terms=ECB_TERMS)
    rates = parse_estr(path.read_bytes(), provenance).data["ESTR"]
    calendar = target2_calendar(range(dates[0].year - 1, dates[-1].year + 2))
    per_period = overnight_returns(rates, dates, day_count=360, calendar=calendar)
    # Only returns between two valuation dates are periods; a return dated on the first date
    # (flows at the start of that day) covers part of one day and is left out.
    periods = twr_returns[pd.DatetimeIndex(twr_returns.index) > pd.Timestamp(dates[0])]
    risk_free = per_period.reindex(pd.DatetimeIndex(periods.index))
    excess = pd.Series(
        periods.to_numpy() - risk_free.to_numpy(), index=risk_free.index, name="excess"
    )
    table = pd.DataFrame(
        {"twr": periods.to_numpy(), "risk_free": risk_free.to_numpy(), "excess": excess},
        index=pd.DatetimeIndex(periods.index, name="period_end"),
    )
    total = float(np.prod(1.0 + risk_free.to_numpy()) - 1.0)
    try:
        sharpe = sharpe_ratio(excess, periods_per_year=12, se_method=SharpeSE.IID_NON_NORMAL)
        reason = ""
    except (UndefinedMetricError, ValidationError) as exc:
        sharpe, reason = None, str(exc)
    return RiskFreeSummary("€STR (ECB)", total, sharpe, reason), table, [provenance]


def _tax_tables(report: TaxReport) -> dict[str, Tagged]:
    """Return the tax report's CSV tables (those with a file name), as described."""
    tables = {}
    for table in report.tables:
        if table.file is None:
            continue
        keys = [c.key for c in table.columns]
        frame = pd.DataFrame(
            [
                {c.key: _csv_cell(cell, c.kind) for cell, c in zip(row, table.columns, strict=True)}
                for row in table.rows
            ],
            columns=keys,
        ).set_index(table.index)
        tables[table.file] = Tagged(frame, "descriptive")
    return tables


def _csv_cell(cell: object, kind: ColumnKind) -> object:
    """Write a cell as the CSV holds it: amounts and shares as floats, the rest as they are."""
    if cell is None:
        return None
    if kind in (ColumnKind.MONEY, ColumnKind.SHARE, ColumnKind.NUMBER):
        return float(cell)  # type: ignore[arg-type]
    return cell


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    files = context.inputs
    to_base, fx_description, fx_provenance, fx_rates = _converter(context, p)
    export = files["transactions"]
    export_provenance = local_provenance(export, dataset="transactions")
    imported = (
        parse_native_csv(export.read_bytes(), export_provenance)
        if p.native
        else parse_broker_csv(
            export.read_bytes(),
            export_provenance,
            load_broker_mapping(files["transactions_mapping"]),
        )
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
    risk_free, risk_free_table, risk_free_provenance = _risk_free(context, dates, twr.returns)
    benchmark, benchmark_provenance = _benchmark(
        context, p, dates, twr.returns, risk_free_table, fx_rates
    )
    check_context = CheckContext(
        as_of=dates[-1],
        history=history,
        valuation=valuation,
        to_base=to_base,
        instruments=instruments,
        prices=prices,
        # With a benchmark, the checks compare the periods between two valuation dates (11.2).
        portfolio_returns=twr.returns if benchmark is None else benchmark.portfolio_returns,
        benchmark_returns=None if benchmark is None else benchmark.benchmark_returns,
        target_weights=p.targets,
        lookthrough=None,
    )
    lookthrough, lookthrough_provenance = _lookthrough(context, p, check_context, instruments)
    total_returns, total_returns_provenance = _total_returns(context)
    held = sorted(
        (i for i, w in check_context.position_weights().items() if w != 0.0), key=lambda i: i.code
    )
    sources = return_levels(
        held,
        prices=prices,
        instruments=instruments,
        total_returns=total_returns,
        distributions=p.distributions,
    )
    # The checks get only the series that differ from the prices, so nothing else changes.
    adjusted = {
        isin: sources.levels[isin]
        for isin in held
        if sources.sources[isin] in (ReturnSource.TOTAL_RETURN_FILE, ReturnSource.DISTRIBUTIONS)
    }
    check_config = load_check_config(files["checks"])
    check_context = replace(check_context, lookthrough=lookthrough, return_levels=adjusted or None)
    checks = run_checks(check_context, check_config)
    risk = None
    if p.risk is not None:
        position_weights = check_context.position_weights()
        risk = compute_risk(
            p.risk,
            as_of=dates[-1],
            value=float(valuation.totals[dates[-1]]),
            base=p.base,
            prices=prices,
            position_weights=position_weights,
            cash_weights=check_context.cash_weights(),
            exposure_currencies={i: check_context.exposure_currency(i) for i in position_weights},
            fx=fx_rates,
            scenarios=load_scenarios(files["scenarios"]) if "scenarios" in files else (),
            levels=sources.levels,
            factors=_factor_returns(context, check_context, p.risk),
        )
    tax_position = None
    if p.tax is not None:
        regime, settings = p.tax
        tax_position = regime.report(
            TaxInputs(
                history=history,
                transactions=imported.transactions,
                instruments=instruments,
                valuation=valuation,
                to_base=to_base,
                as_of=dates[-1],
                prices=prices,
                max_price_age_days=p.max_price_age_days,
            ),
            settings,
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
            *risk_free_provenance,
            *total_returns_provenance,
            *benchmark_provenance,
            *(
                [local_provenance(files["factors"], dataset="factors")]
                if "factors" in files
                else []
            ),
        ],
        instruments=instruments,
        import_notes=list(imported.notes),
        return_frequency=(Frequency.MONTHLY, 12.0) if p.monthly else None,
        checks=checks,
        lookthrough=lookthrough,
        risk=None if risk is None else risk.summary,
        projection=None if plan is None else plan[0].result,
        risk_free=risk_free,
        tax=tax_position,
        return_sources=None if risk is None else sources.sources,
        benchmark=None if benchmark is None else benchmark.summary,
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
    caveats = [DECLARED_COST] if any(t.cost is not None for t in imported.transactions) else []
    figures = {}
    if tax_position is not None:
        tables |= _tax_tables(tax_position)
        if tax_position.notice is not None:
            caveats.append(tax_position.notice)
        scalars |= {
            name: Tagged(float(value), "descriptive")
            for name, value in tax_position.scalars.items()
        }
    if benchmark is not None:
        tables["benchmark"] = Tagged(benchmark.table, "descriptive")
        scalars |= {name: Tagged(value, "descriptive") for name, value in benchmark.scalars.items()}
    if risk_free is not None and risk_free_table is not None:
        tables["risk_free"] = Tagged(risk_free_table, "descriptive")
        scalars["risk_free_total"] = Tagged(risk_free.total, "descriptive")
        if risk_free.sharpe is not None:
            scalars["sharpe_ratio"] = Tagged(risk_free.sharpe.value, "descriptive")
            scalars["sharpe_ratio_se"] = Tagged(risk_free.sharpe.standard_error, "descriptive")
    if risk is not None:
        tables |= risk.tables
        tables["return_sources"] = Tagged(
            pd.DataFrame(
                {
                    "source": [sources.sources[i].value for i in held],
                    "income_included": [sources.sources[i].income_included for i in held],
                },
                index=pd.Index([i.code for i in held], name="holding"),
            ),
            "descriptive",
        )
        scalars |= risk.scalars
    uses_returns = risk is not None or any(
        check_id.startswith("diversification.") and thresholds.enabled
        for check_id, thresholds in check_config.checks.items()
    )
    note = excluded_note(
        sources.sources, {isin: instrument.name for isin, instrument in instruments.items()}
    )
    if uses_returns and note is not None:
        caveats.append(note)
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
    description=(
        "HTML portfolio report with health checks from a broker export or a native "
        "transactions file (descriptive)"
    ),
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
