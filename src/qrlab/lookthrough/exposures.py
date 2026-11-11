r"""Portfolio exposures through the holdings of its funds.

A fund at portfolio weight :math:`w_f` holding :math:`h_{f,i}` of security :math:`i` contributes
:math:`w_f h_{f,i}` to that security's look-through weight. Exposures group these weights by a
:class:`Dimension`. Nothing is redistributed:

- with :attr:`WeightTreatment.AS_REPORTED` the part of a fund's weight its holdings do not
  explain (:math:`w_f (1 - \sum_i h_{f,i})`) is an ``"unexplained"`` bucket; with
  :attr:`WeightTreatment.NORMALISED` the holdings are divided by their sum (explicitly);
- unknown fields of a holding go to an ``"unknown"`` bucket;
- funds without a holdings snapshot go to a ``"not looked through"`` bucket;
- cash is its own bucket in every dimension except currency.

Direct positions (non-fund instruments) look through to themselves, with the master-data
domicile as country and the instrument currency. Weights come from the caller (for example
``CheckContext.position_weights``) and are over the total portfolio value including cash.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.instruments.holdings import HoldingsSnapshot, normalised_weights
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import FUND_TYPES, Instrument

__all__ = [
    "CASH",
    "NOT_LOOKED_THROUGH",
    "SPECIAL_BUCKETS",
    "UNEXPLAINED",
    "UNKNOWN",
    "Dimension",
    "LookThrough",
    "WeightTreatment",
    "look_through",
]

UNKNOWN = "unknown"
UNEXPLAINED = "unexplained"
NOT_LOOKED_THROUGH = "not looked through"
CASH = "cash"
SPECIAL_BUCKETS = frozenset({UNKNOWN, UNEXPLAINED, NOT_LOOKED_THROUGH, CASH})
"""Buckets that are never one country, sector, currency, security or issuer."""

ROW_COLUMNS = (
    "source",
    "kind",
    "security",
    "isin",
    "name",
    "country",
    "sector",
    "currency",
    "underlying_currency",
    "issuer",
    "weight",
)
"""Columns of :attr:`LookThrough.rows`."""


class WeightTreatment(Enum):
    """How a fund's reported holding weights are used."""

    AS_REPORTED = "as_reported"
    NORMALISED = "normalised"


class Dimension(Enum):
    """What exposures are grouped by."""

    COUNTRY = "country"
    SECTOR = "sector"
    CURRENCY = "currency"  # hedge currency for hedged share classes
    UNDERLYING_CURRENCY = "underlying_currency"  # currencies of the holdings, ignoring hedging
    SECURITY = "security"
    ISSUER = "issuer"


@dataclass(frozen=True)
class LookThrough:
    """Look-through weights of a portfolio on ``as_of``.

    Attributes
    ----------
    as_of
        Valuation date of the portfolio weights.
    treatment
        How reported holding weights were used.
    rows
        One row per piece of exposure, with :data:`ROW_COLUMNS`. ``kind`` is ``"holding"``,
        ``"direct"``, ``"cash"``, ``"unexplained"`` or ``"not_looked_through"``; ``source`` is the
        fund or position ISIN code, or ``"cash"``. ``security`` is the holding ISIN, or
        ``"name:<name>"`` when the holding has no ISIN.
    snapshot_dates
        Holdings date of every fund looked through.
    issuer_mapped
        Whether an issuer map was given; without one, issuers are securities.
    """

    as_of: date
    treatment: WeightTreatment
    rows: pd.DataFrame
    snapshot_dates: Mapping[Isin, date]
    issuer_mapped: bool

    def exposure(self, dimension: Dimension) -> pd.Series:
        """Total weight per bucket, largest first (ties by name), special buckets included."""
        labels = [_bucket(row, dimension) for row in self.rows.itertuples(index=False)]
        grouped = self.rows["weight"].groupby(pd.Index(labels, name=dimension.value)).sum()
        order = sorted(grouped.index, key=lambda k: (-float(grouped[k]), str(k)))
        return grouped.loc[order].rename("weight")

    def largest(self, dimension: Dimension) -> tuple[str, float] | None:
        """Largest bucket that is not a special bucket, or ``None`` if there is none."""
        exposure = self.exposure(dimension)
        regular = exposure[[k not in SPECIAL_BUCKETS for k in exposure.index]]
        if regular.empty:
            return None
        return str(regular.index[0]), float(regular.iloc[0])

    def bucket(self, dimension: Dimension, name: str) -> float:
        """Weight of one bucket (0 if absent)."""
        exposure = self.exposure(dimension)
        return float(exposure[name]) if name in exposure.index else 0.0


def look_through(
    *,
    as_of: date,
    position_weights: Mapping[Isin, float],
    cash_weights: Mapping[Currency, float],
    instruments: Mapping[Isin, Instrument],
    snapshots: Mapping[Isin, HoldingsSnapshot],
    treatment: WeightTreatment,
    issuers: Mapping[Isin, str] | None,
) -> LookThrough:
    """Look through the funds of a portfolio.

    Parameters
    ----------
    as_of
        Valuation date of the weights.
    position_weights, cash_weights
        Portfolio weights by ISIN and cash weights by currency, over the total value.
    instruments
        Master data; non-fund instruments are direct positions.
    snapshots
        Holdings by fund ISIN. Each snapshot's ``fund`` must match its key. Snapshots dated
        after ``as_of`` raise (look-ahead). Snapshots of funds not held are ignored.
    treatment
        How reported holding weights are used.
    issuers
        Optional map from security ISIN to issuer name.
    """
    for key, snapshot in snapshots.items():
        if snapshot.fund != key:
            raise ValidationError(f"snapshot for {snapshot.fund.code} stored under {key.code}")
        if snapshot.as_of > as_of:
            raise ValidationError(
                f"holdings of {key.code} are dated {snapshot.as_of}, after {as_of}"
            )
    issuer_map = dict(issuers or {})
    rows: list[dict[str, object]] = []
    dates: dict[Isin, date] = {}
    for isin, weight in sorted(position_weights.items(), key=lambda item: item[0].code):
        instrument = instruments.get(isin)
        if isin in snapshots:
            dates[isin] = snapshots[isin].as_of
            rows += _fund_rows(isin, weight, snapshots[isin], instrument, treatment, issuer_map)
        elif instrument is not None and instrument.instrument_type not in FUND_TYPES:
            rows.append(
                _row(
                    source=isin.code,
                    kind="direct",
                    security=isin.code,
                    isin=isin.code,
                    name=instrument.name,
                    country=instrument.domicile,
                    currency=instrument.currency.code,
                    issuer=issuer_map.get(isin, isin.code),
                    weight=weight,
                )
            )
        else:
            rows.append(_row(source=isin.code, kind="not_looked_through", weight=weight))
    for currency, weight in sorted(cash_weights.items(), key=lambda item: item[0].code):
        rows.append(_row(source=CASH, kind="cash", currency=currency.code, weight=weight))
    frame = pd.DataFrame(rows, columns=list(ROW_COLUMNS))
    frame["weight"] = frame["weight"].astype("float64")
    return LookThrough(as_of, treatment, frame, dates, issuers is not None)


def _fund_rows(
    fund: Isin,
    weight: float,
    snapshot: HoldingsSnapshot,
    instrument: Instrument | None,
    treatment: WeightTreatment,
    issuers: Mapping[Isin, str],
) -> list[dict[str, object]]:
    table = snapshot.holdings
    if treatment is WeightTreatment.NORMALISED:
        holding_weights = normalised_weights(snapshot)
    else:
        holding_weights = table["weight"]
    hedge = instrument.hedged_to.code if instrument and instrument.hedged_to else None
    rows = []
    for holding, h in zip(table.itertuples(index=False), holding_weights, strict=True):
        isin = holding.isin
        security = isin if isin is not None else f"name:{holding.name}"
        issuer = issuers.get(Isin(str(isin)), security) if isin is not None else security
        rows.append(
            _row(
                source=fund.code,
                kind="holding",
                security=security,
                isin=isin,
                name=holding.name,
                country=holding.country,
                sector=holding.sector,
                currency=hedge or holding.currency,
                underlying_currency=holding.currency,
                issuer=issuer,
                weight=weight * float(h),
            )
        )
    if treatment is WeightTreatment.AS_REPORTED:
        residual = 1.0 - float(table["weight"].sum())
        if residual != 0.0:
            rows.append(_row(source=fund.code, kind="unexplained", weight=weight * residual))
    return rows


def _row(*, source: str, kind: str, weight: float, **fields: object) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(ROW_COLUMNS)
    row.update(source=source, kind=kind, weight=weight, **fields)
    if kind == "direct":
        row["underlying_currency"] = row["currency"]
    if kind == "cash":
        row["underlying_currency"] = row["currency"]
    return row


_KIND_BUCKETS = {"unexplained": UNEXPLAINED, "not_looked_through": NOT_LOOKED_THROUGH}


def _bucket(row: object, dimension: Dimension) -> str:
    kind = row.kind  # type: ignore[attr-defined]
    if kind in _KIND_BUCKETS:
        return _KIND_BUCKETS[kind]
    if kind == "cash" and dimension not in {Dimension.CURRENCY, Dimension.UNDERLYING_CURRENCY}:
        return CASH
    value = getattr(row, dimension.value)
    return UNKNOWN if value is None or pd.isna(value) else str(value)
