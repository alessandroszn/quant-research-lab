r"""Stress tests of today's portfolio: historical replays and hypothetical shocks.

Each position is treated by the first method that applies; the method is reported:

- **direct** (historical): its own return series covers the window,
  :math:`R_i=\prod_t(1+r_{i,t})-1`; the series currency is explicit, and the currency effect
  :math:`X` applied is that of the series currency (0 for a series in the base currency);
- **proxy**: it has betas and the factors cover the window. Each period is mapped first,
  :math:`r_{i,t}=\beta_i^\top f_t` (no alpha, no residual), then compounded. Hypothetical factor
  shocks map linearly, :math:`R_i=\beta_i^\top F`. The currency effect is that of the position's
  exposure currency (the hedge currency of a hedged class);
- **shock** (hypothetical): a shock given for the position itself;
- **currency only** (hypothetical, no factor shock): local return 0, currency effect applied;
- **not covered**: none of the above. Its weight is reported and excluded; it is never assumed
  to lose 0.

The base return is :math:`(1+R_i)(1+X)-1`; foreign cash returns :math:`X_c`. The portfolio
return is :math:`\sum_i w_i R^{base}_i + \sum_c w_c X_c` over the covered weight, and the money
figure is that return times the portfolio value. A stress test is a "what if" on today's
weights, not a forecast.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.core.series import NanPolicy, validate_frame, validate_series
from qrlab.instruments.identifiers import Isin
from qrlab.scenarios.definitions import HistoricalScenario, HypotheticalScenario, Scenario

__all__ = [
    "MarketData",
    "PositionResult",
    "PositionSeries",
    "ScenarioResult",
    "StressPortfolio",
    "run_scenario",
]


@dataclass(frozen=True)
class StressPortfolio:
    """Today's portfolio as the stress tests see it.

    Parameters
    ----------
    as_of, value
        Date and total value of the portfolio (base currency, including cash).
    position_weights, cash_weights
        Weights over the total value.
    exposure_currencies
        Currency each position is exposed to (the hedge currency of a hedged class).
    """

    as_of: date
    value: Money
    position_weights: Mapping[Isin, float]
    cash_weights: Mapping[Currency, float]
    exposure_currencies: Mapping[Isin, Currency]

    def __post_init__(self) -> None:
        """Every position needs an exposure currency, and weights must sum to 1."""
        missing = sorted(i.code for i in self.position_weights if i not in self.exposure_currencies)
        if missing:
            raise ValidationError(f"no exposure currency for {missing}")
        total = sum(self.position_weights.values()) + sum(self.cash_weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValidationError(f"weights must sum to 1, got {total}")

    @property
    def base(self) -> Currency:
        """Base currency."""
        return self.value.currency


@dataclass(frozen=True)
class PositionSeries:
    """Simple returns of one position, in the currency they are measured in."""

    returns: pd.Series
    currency: Currency


@dataclass(frozen=True)
class MarketData:
    """Return series for historical replays and betas for proxies.

    Parameters
    ----------
    positions
        Own return series by position.
    factors
        Factor returns (columns are factor names), or an empty frame.
    betas
        Positions (ISIN codes) by factors, or ``None``. Columns must be factors in ``factors``.
    fx
        Return of one unit of each foreign currency measured in the base currency.
    """

    positions: Mapping[Isin, PositionSeries]
    factors: pd.DataFrame
    betas: pd.DataFrame | None
    fx: Mapping[Currency, pd.Series]


@dataclass(frozen=True)
class PositionResult:
    """Result of one position or one cash balance."""

    holding: str
    weight: float
    method: str
    local_return: float | None
    fx_return: float | None
    base_return: float | None

    @property
    def contribution(self) -> float | None:
        """Weight times base return, or ``None`` if not covered."""
        return None if self.base_return is None else self.weight * self.base_return


@dataclass(frozen=True)
class ScenarioResult:
    """Portfolio result of one scenario."""

    scenario: Scenario
    portfolio_return: float
    pnl: Money
    not_covered_weight: float
    first_date: date | None
    last_date: date | None
    rows: tuple[PositionResult, ...]
    notes: tuple[str, ...]


def run_scenario(
    scenario: Scenario, portfolio: StressPortfolio, market: MarketData
) -> ScenarioResult:
    """Apply ``scenario`` to ``portfolio``."""
    betas = _betas(market)
    if isinstance(scenario, HistoricalScenario):
        return _historical(scenario, portfolio, market, betas)
    return _hypothetical(scenario, portfolio, betas)


# --------------------------------------------------------------------------- historical
def _historical(
    scenario: HistoricalScenario,
    portfolio: StressPortfolio,
    market: MarketData,
    betas: pd.DataFrame | None,
) -> ScenarioResult:
    used: list[pd.Timestamp] = []
    notes: list[str] = []
    fx: dict[Currency, float | None] = {}

    def currency_return(currency: Currency) -> float | None:
        if currency == portfolio.base:
            return 0.0
        if currency not in fx:
            series = market.fx.get(currency)
            window = None if series is None else _window(series, scenario, f"fx {currency.code}")
            fx[currency] = None if window is None else _compound(window, used)
            if window is None:
                notes.append(f"no {currency.code} rates cover the window")
        return fx[currency]

    factors = None
    if betas is not None:
        absent = sorted(set(map(str, betas.columns)) - set(map(str, market.factors.columns)))
        if absent:
            notes.append(f"factor returns do not include {absent}: no proxies")
        else:
            frame = validate_frame(
                market.factors[betas.columns], nan_policy=NanPolicy.KEEP, name="factors"
            )
            factors = _frame_window(frame, scenario)
    rows: list[PositionResult] = []
    for isin, weight in sorted(portfolio.position_weights.items(), key=lambda i: i[0].code):
        own = market.positions.get(isin)
        window = None if own is None else _window(own.returns, scenario, isin.code)
        if own is not None and window is not None:
            local, method, currency = _compound(window, used), "direct", own.currency
        elif betas is not None and factors is not None and isin.code in betas.index:
            exposure = betas.loc[isin.code].to_numpy(dtype=np.float64)
            mapped = pd.Series(factors.to_numpy() @ exposure, index=factors.index)
            local, method = _compound(mapped, used), "proxy"
            currency = portfolio.exposure_currencies[isin]
        else:
            rows.append(PositionResult(isin.code, weight, "not covered", None, None, None))
            continue
        rows.append(_row(isin.code, weight, method, local, currency_return(currency)))
    rows += _cash_rows(portfolio, currency_return)
    first = min(used).date() if used else None
    last = max(used).date() if used else None
    return _result(scenario, portfolio, rows, first, last, notes)


def _window(series: pd.Series, scenario: HistoricalScenario, name: str) -> pd.Series | None:
    """Return the returns dated in (start, end] if the series covers the window without gaps."""
    values = validate_series(series, nan_policy=NanPolicy.KEEP, name=name)
    mask = _covering(values.index, scenario)
    if mask is None or bool(values[mask].isna().any()):
        return None
    return values[mask]


def _frame_window(frame: pd.DataFrame, scenario: HistoricalScenario) -> pd.DataFrame | None:
    """Rows dated in (start, end] if every column covers the whole window without gaps."""
    mask = _covering(frame.index, scenario)
    if mask is None or bool(frame[mask].isna().to_numpy().any()):
        return None
    return frame[mask]


def _covering(index: pd.Index, scenario: HistoricalScenario) -> np.ndarray | None:
    start, end = pd.Timestamp(scenario.start), pd.Timestamp(scenario.end)
    if len(index) == 0 or index[0] > start or index[-1] < end:
        return None
    mask = np.asarray((index > start) & (index <= end))
    return mask if mask.any() else None


def _compound(returns: pd.Series, used: list[pd.Timestamp]) -> float:
    used.extend([returns.index[0], returns.index[-1]])
    return float(np.prod(1.0 + returns.to_numpy(dtype=np.float64))) - 1.0


# --------------------------------------------------------------------------- hypothetical
def _hypothetical(
    scenario: HypotheticalScenario, portfolio: StressPortfolio, betas: pd.DataFrame | None
) -> ScenarioResult:
    if portfolio.base in scenario.currencies:
        raise ValidationError(f"{scenario.id}: the base currency cannot be shocked")
    known = set() if betas is None else set(betas.columns)
    unknown = sorted(set(scenario.factors) - known)
    if unknown:
        raise ValidationError(f"{scenario.id}: no betas for factors {unknown}")
    shock = pd.Series({f: float(scenario.factors.get(f, 0.0)) for f in sorted(known)})

    def currency_return(currency: Currency) -> float:
        return 0.0 if currency == portfolio.base else float(scenario.currencies.get(currency, 0.0))

    rows: list[PositionResult] = []
    for isin, weight in sorted(portfolio.position_weights.items(), key=lambda i: i[0].code):
        currency = portfolio.exposure_currencies[isin]
        if isin in scenario.positions:
            local, method = float(scenario.positions[isin]), "shock"
        elif not scenario.factors:
            local, method = 0.0, "currency only"
        elif betas is not None and isin.code in betas.index:
            exposure = betas.loc[isin.code].reindex(shock.index).to_numpy(dtype=np.float64)
            local, method = float(exposure @ shock.to_numpy()), "proxy"
        else:
            rows.append(PositionResult(isin.code, weight, "not covered", None, None, None))
            continue
        rows.append(_row(isin.code, weight, method, local, currency_return(currency)))
    rows += _cash_rows(portfolio, currency_return)
    return _result(scenario, portfolio, rows, None, None, [])


# --------------------------------------------------------------------------- shared
def _betas(market: MarketData) -> pd.DataFrame | None:
    if market.betas is None:
        return None
    if market.betas.isna().to_numpy().any():
        raise ValidationError("betas must not contain missing values")
    return market.betas.astype("float64")


def _row(
    holding: str, weight: float, method: str, local: float, fx: float | None
) -> PositionResult:
    if fx is None:
        return PositionResult(holding, weight, "not covered", local, None, None)
    return PositionResult(holding, weight, method, local, fx, (1.0 + local) * (1.0 + fx) - 1.0)


def _cash_rows(
    portfolio: StressPortfolio, currency_return: Callable[[Currency], float | None]
) -> list[PositionResult]:
    rows = []
    for currency, weight in sorted(portfolio.cash_weights.items(), key=lambda i: i[0].code):
        fx = currency_return(currency)
        method = "cash" if fx is not None else "not covered"
        rows.append(PositionResult(f"cash {currency.code}", weight, method, 0.0, fx, fx))
    return rows


def _result(
    scenario: Scenario,
    portfolio: StressPortfolio,
    rows: list[PositionResult],
    first: date | None,
    last: date | None,
    notes: list[str],
) -> ScenarioResult:
    covered = [r for r in rows if r.base_return is not None]
    not_covered = sum(r.weight for r in rows if r.base_return is None)
    total = sum(r.weight * r.base_return for r in covered if r.base_return is not None)
    if not_covered > 0:
        notes.append(f"{not_covered:.2%} of the portfolio is not covered and is excluded")
    amount = portfolio.value.amount * Decimal(repr(total))
    pnl = Money(amount.quantize(Decimal("0.01")), portfolio.base)
    return ScenarioResult(scenario, total, pnl, not_covered, first, last, tuple(rows), tuple(notes))
