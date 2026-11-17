"""Experiment kind ``scenario_analysis``: historical and hypothetical stress tests of holdings.

Inputs (CSV files read with ``[parameters.csv_format]``):

- ``holdings`` (required): columns ``holding``, ``type`` (``position`` or ``cash``), ``weight``
  and ``currency`` (exposure currency of a position, currency of a cash balance); weights sum
  to 1;
- ``scenarios`` (required): the scenarios TOML of phase 3.2;
- ``position_returns`` (optional): dated returns, one column per position ISIN, measured in
  ``position_returns_currency`` and declared ``"total_return"`` or ``"price"`` in
  ``position_returns_price_type`` (required, like the currency, even without the file);
- ``factors`` (optional): dated factor returns, one column per factor;
- ``betas`` (optional): column ``holding`` (ISIN) and one column per factor;
- ``fx`` (optional): dated returns of one unit of each foreign currency in the base currency.

The engine of phase 3.2 decides, per position, between its own series, a factor proxy, a direct
shock, the currency effect only, or "not covered" (reported, never assumed to lose 0). Stress
tests are "what if" on today's weights, not forecasts: every output is ``descriptive``.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.user_csv import PriceType
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds import _fields as f
from qrlab.experiments.kinds._frames import (
    price_type,
    read_returns,
    returns_format,
    returns_notice,
)
from qrlab.experiments.kinds._params import day, number, text
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.experiments.schema import KindSchema
from qrlab.instruments.identifiers import Isin
from qrlab.scenarios.definitions import HistoricalScenario, load_scenarios
from qrlab.scenarios.engine import MarketData, PositionSeries, StressPortfolio, run_scenario

__all__ = ["CAVEATS", "KIND", "SCHEMA"]

CAVEATS = "What-if stress tests on today's weights. Not forecasts or probabilities of loss."

_PARAMETERS = (
    "as_of",
    "value",
    "currency",
    "csv_format",
    "position_returns_currency",
    "position_returns_price_type",
)
_OPTIONAL_INPUTS = ("position_returns", "factors", "betas", "fx")


@dataclass(frozen=True)
class _Parameters:
    as_of: date
    value: float
    currency: Currency
    csv_format: Mapping[str, str]
    returns_currency: Currency
    returns_price_type: PriceType


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    value = number(parameters, "value")
    if not value > 0:
        raise ValidationError("value must be positive")
    return _Parameters(
        as_of=day(parameters, "as_of"),
        value=value,
        currency=Currency(text(parameters, "currency")),
        csv_format=returns_format(parameters, "csv_format"),
        returns_currency=Currency(text(parameters, "position_returns_currency")),
        returns_price_type=price_type(parameters, "position_returns_price_type"),
    )


def _plain_csv(path: Path, fmt: Mapping[str, str]) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(path.read_bytes()), sep=fmt["delimiter"], decimal=fmt["decimal_separator"]
    )


def _portfolio(path: Path, p: _Parameters) -> StressPortfolio:
    frame = _plain_csv(path, p.csv_format)
    required = ["holding", "type", "weight", "currency"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValidationError(f"holdings file lacks columns {missing}")
    positions: dict[Isin, float] = {}
    cash: dict[Currency, float] = {}
    exposures: dict[Isin, Currency] = {}
    for holding, kind, raw_weight, code in zip(
        frame["holding"],
        frame["type"],
        frame["weight"].astype("float64"),
        frame["currency"],
        strict=True,
    ):
        weight = float(raw_weight)
        currency = Currency(str(code))
        if kind == "position":
            isin = Isin(str(holding))
            if isin in positions:
                raise ValidationError(f"holding {isin.code} is listed twice")
            positions[isin] = weight
            exposures[isin] = currency
        elif kind == "cash":
            cash[currency] = cash.get(currency, 0.0) + weight
        else:
            raise ValidationError(f"type must be 'position' or 'cash', got {kind!r}")
    return StressPortfolio(
        as_of=p.as_of,
        value=Money(Decimal(repr(p.value)), p.currency),
        position_weights=positions,
        cash_weights=cash,
        exposure_currencies=exposures,
    )


def _market(inputs: Mapping[str, Path], p: _Parameters) -> MarketData:
    fmt = p.csv_format
    positions = {}
    if "position_returns" in inputs:
        frame = read_returns(inputs["position_returns"].read_bytes(), fmt)
        for column in frame.columns:
            positions[Isin(str(column))] = PositionSeries(
                frame[column].dropna(), p.returns_currency
            )
    factors = (
        read_returns(inputs["factors"].read_bytes(), fmt)
        if "factors" in inputs
        else pd.DataFrame(index=pd.DatetimeIndex([], name="date"))
    )
    betas = None
    if "betas" in inputs:
        betas = _plain_csv(inputs["betas"], fmt)
        if "holding" not in betas.columns:
            raise ValidationError("betas file needs a 'holding' column")
        betas = betas.set_index("holding").astype("float64")
    fx = {}
    if "fx" in inputs:
        frame = read_returns(inputs["fx"].read_bytes(), fmt)
        fx = {Currency(str(c)): frame[c].dropna() for c in frame.columns}
    return MarketData(positions=positions, factors=factors, betas=betas, fx=fx)


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    portfolio = _portfolio(context.inputs["holdings"], p)
    market = _market(context.inputs, p)
    scenarios = load_scenarios(context.inputs["scenarios"])
    summary, rows = [], []
    for scenario in scenarios:
        result = run_scenario(scenario, portfolio, market)
        summary.append(
            {
                "scenario": scenario.id,
                "description": scenario.description,
                "kind": "historical"
                if isinstance(scenario, HistoricalScenario)
                else "hypothetical",
                "portfolio_return": result.portfolio_return,
                "pnl": float(result.pnl.amount),
                "currency": result.pnl.currency.code,
                "not_covered_weight": result.not_covered_weight,
                "first_date": result.first_date,
                "last_date": result.last_date,
                "notes": " ".join(result.notes),
            }
        )
        rows += [
            {
                "scenario": scenario.id,
                "holding": r.holding,
                "weight": r.weight,
                "method": r.method,
                "local_return": r.local_return,
                "fx_return": r.fx_return,
                "base_return": r.base_return,
                "contribution": r.contribution,
            }
            for r in result.rows
        ]
    return ExperimentOutput(
        tables={
            "scenarios": Tagged(pd.DataFrame(summary).set_index("scenario"), "descriptive"),
            "positions": Tagged(pd.DataFrame(rows), "descriptive"),
        },
        scalars={"scenarios_run": Tagged(float(len(summary)), "descriptive")},
        notice=returns_notice(
            CAVEATS, p.returns_price_type if "position_returns" in context.inputs else None
        ),
    )


SCHEMA = KindSchema(
    inputs=(
        f.file(
            "holdings",
            "CSV of today's holdings: columns holding, type (position or cash), weight and "
            "currency; the weights sum to 1.",
            "CSV delle posizioni di oggi: colonne holding, type (position o cash), weight e "
            "currency; i pesi sommano a 1.",
        ),
        f.file(
            "scenarios",
            "TOML file of the historical and hypothetical scenarios to run.",
            "File TOML degli scenari storici e ipotetici da eseguire.",
        ),
        f.file(
            "position_returns",
            "CSV of dated returns, one column per position ISIN, in position_returns_currency. "
            "Absent: no position uses its own history.",
            "CSV di rendimenti datati, una colonna per ISIN di posizione, in "
            "position_returns_currency. Assente: nessuna posizione usa la propria storia.",
            required=False,
        ),
        f.file(
            "factors",
            "CSV of dated factor returns, one column per factor. Absent: no factor proxies.",
            "CSV di rendimenti datati dei fattori, una colonna per fattore. Assente: nessuna "
            "approssimazione con fattori.",
            required=False,
        ),
        f.file(
            "betas",
            "CSV with a holding column (ISIN) and one beta column per factor. Absent: no "
            "factor proxies.",
            "CSV con una colonna holding (ISIN) e una colonna di beta per fattore. Assente: "
            "nessuna approssimazione con fattori.",
            required=False,
        ),
        f.file(
            "fx",
            "CSV of dated returns of one unit of each foreign currency in the base currency. "
            "Absent: no historical exchange-rate returns.",
            "CSV di rendimenti datati di un'unità di ogni valuta estera nella valuta di base. "
            "Assente: nessun rendimento storico dei cambi.",
            required=False,
        ),
    ),
    parameters=(
        f.day(
            "as_of",
            "Date of the holdings.",
            "Data delle posizioni.",
        ),
        f.number(
            "value",
            "Value of the portfolio on as_of.",
            "Valore del portafoglio alla data as_of.",
            minimum=0.0,
            open_minimum=True,
            unit="currency units",
        ),
        f.currency(
            "currency",
            "Base currency of the portfolio's value.",
            "Valuta di base del valore del portafoglio.",
        ),
        f.table(
            "csv_format",
            "How the CSV inputs are written: date column and format, delimiter and decimal "
            "separator.",
            "Come sono scritti i CSV in ingresso: colonna e formato delle date, separatore di "
            "campo e separatore decimale.",
            f.RETURNS_FORMAT.fields,
        ),
        f.currency(
            "position_returns_currency",
            "Currency in which the position returns are measured (required even without the file).",
            "Valuta in cui sono misurati i rendimenti delle posizioni (richiesta anche senza il "
            "file).",
        ),
        f.choice(
            "position_returns_price_type",
            "Whether the position returns include dividends: total_return, or price (dividends "
            "excluded); required even without the file.",
            "Se i rendimenti delle posizioni includono i dividendi: total_return, oppure price "
            "(dividendi esclusi); richiesto anche senza il file.",
            f.RETURNS_PRICE_TYPE.choices,
        ),
    ),
)
"""What ``scenario_analysis`` accepts (design note 12.1)."""

KIND = ExperimentKind(
    name="scenario_analysis",
    description="Historical and hypothetical stress tests of today's holdings (descriptive)",
    inputs=("holdings", "scenarios"),
    needs_seed=False,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
    optional_inputs=_OPTIONAL_INPUTS,
    schema=SCHEMA,
)
