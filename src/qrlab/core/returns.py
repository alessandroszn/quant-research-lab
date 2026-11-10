r"""Return conventions: price to returns, simple and log returns, compounding, aggregation.

Every function takes the return kind explicitly (:class:`ReturnKind`). Inputs are validated
with :mod:`qrlab.core.series`; nothing is forward-filled, aligned or dropped silently.

Definitions, for a price :math:`P_t`:

- simple return :math:`R_t = P_t / P_{t-1} - 1`;
- log return :math:`r_t = \ln(P_t / P_{t-1}) = \ln(1 + R_t)`;
- compounding over periods: :math:`\prod_t (1 + R_t) - 1` for simple returns and
  :math:`\sum_t r_t` for log returns.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar, cast, overload

import numpy as np
import pandas as pd

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, require_same_index, validate_frame, validate_series

__all__ = [
    "AggregatedReturns",
    "ReturnKind",
    "aggregate_returns",
    "compound",
    "convert_return_currency",
    "excess_returns",
    "log_to_simple",
    "prices_to_returns",
    "simple_to_log",
    "wealth_index",
]

_T = TypeVar("_T", pd.Series, pd.DataFrame)


class ReturnKind(Enum):
    """Whether returns are simple (arithmetic) or logarithmic (continuously compounded)."""

    SIMPLE = "simple"
    LOG = "log"


@dataclass(frozen=True)
class AggregatedReturns(Generic[_T]):
    """Returns aggregated to a lower frequency.

    Attributes
    ----------
    returns
        Compounded return per bucket, labelled by period end. NaN where the bucket has fewer
        than ``min_periods`` observations or contains a NaN.
    counts
        Number of input observations (rows) in each bucket.
    """

    returns: _T
    counts: pd.Series


def prices_to_returns(prices: _T, *, kind: ReturnKind) -> _T:
    """Convert a price series or frame to returns.

    Parameters
    ----------
    prices
        Strictly positive prices on a validated index. NaNs are allowed and propagate: a NaN
        price makes the two adjacent returns NaN. Nothing is forward-filled.
    kind
        Return kind of the output.

    Returns
    -------
    Series or DataFrame
        Returns indexed by the later timestamp of each pair; the first observation is dropped.

    Raises
    ------
    ValidationError
        If any non-missing price is zero or negative, or the input is not a valid time series.
    """
    _check_kind(kind)
    valid = _validate(prices, NanPolicy.KEEP, "prices")
    if (valid.to_numpy() <= 0).any():
        raise ValidationError("prices must be strictly positive")
    ratio = (valid / valid.shift(1)).iloc[1:]
    if kind is ReturnKind.SIMPLE:
        return ratio - 1.0
    return _ufunc(np.log, ratio)


def simple_to_log(returns: _T) -> _T:
    r"""Convert simple returns to log returns, :math:`\ln(1 + R)`.

    Raises
    ------
    ValidationError
        If any return is less than or equal to -1 (wealth would be zero or negative, so the log
        return is undefined).
    """
    valid = _validate(returns, NanPolicy.KEEP, "returns")
    if (valid.to_numpy() <= -1.0).any():
        raise ValidationError("simple returns <= -1 have no log-return equivalent")
    return _ufunc(np.log1p, valid)


def log_to_simple(returns: _T) -> _T:
    r"""Convert log returns to simple returns, :math:`e^{r} - 1`."""
    valid = _validate(returns, NanPolicy.KEEP, "returns")
    return _ufunc(np.expm1, valid)


def excess_returns(returns: _T, risk_free: pd.Series, *, kind: ReturnKind) -> _T:
    """Subtract a per-period risk-free rate from returns.

    Parameters
    ----------
    returns
        Asset returns (series, or frame with one column per asset).
    risk_free
        Risk-free return for the same periods, frequency and kind as ``returns``. Its index must
        be identical: indexes are never intersected or aligned silently.
    kind
        Return kind of both inputs. For both kinds the excess return is the difference
        ``returns - risk_free``.

    Raises
    ------
    AlignmentError
        If the indexes differ.
    """
    _check_kind(kind)
    valid = _validate(returns, NanPolicy.KEEP, "returns")
    rf = validate_series(risk_free, nan_policy=NanPolicy.KEEP, name="risk_free")
    require_same_index(valid, rf)
    return _restore(_as_frame(valid).sub(rf, axis=0), like=valid)


def convert_return_currency(returns: _T, fx: pd.Series, *, kind: ReturnKind) -> _T:
    r"""Re-express returns in another currency with dated exchange rates.

    ``fx`` is the price of one unit of the returns' currency in the target currency (e.g. USD
    per EUR to turn EUR returns into USD returns), observed at the same dates as the returns
    **plus one earlier date** (the start of the first period):

    - simple: :math:`1 + r^{tgt}_t = (1 + r^{src}_t)\, fx_t / fx_{t-1}`;
    - log: :math:`r^{tgt}_t = r^{src}_t + \ln(fx_t / fx_{t-1})`.

    Raises
    ------
    ValidationError
        If ``fx`` does not have exactly one more observation than ``returns``, contains NaN,
        or is not strictly positive.
    AlignmentError
        If ``fx`` without its first observation does not have the returns' index.
    """
    _check_kind(kind)
    valid = _validate(returns, NanPolicy.KEEP, "returns")
    rates = validate_series(fx, nan_policy=NanPolicy.RAISE, name="fx")
    if len(rates) != len(valid) + 1:
        raise ValidationError(
            f"fx must have one more observation than returns ({len(rates)} vs {len(valid)})"
        )
    if (rates.to_numpy() <= 0).any():
        raise ValidationError("fx rates must be strictly positive")
    require_same_index(valid, rates.iloc[1:])
    relative = pd.Series(rates.to_numpy()[1:] / rates.to_numpy()[:-1], index=valid.index)
    frame = _as_frame(valid)
    if kind is ReturnKind.SIMPLE:
        converted = (1.0 + frame).mul(relative, axis=0) - 1.0
    else:
        converted = frame.add(_ufunc(np.log, relative), axis=0)
    return _restore(converted, like=valid)


@overload
def compound(returns: pd.Series, *, kind: ReturnKind) -> float: ...
@overload
def compound(returns: pd.DataFrame, *, kind: ReturnKind) -> pd.Series: ...
def compound(returns: pd.Series | pd.DataFrame, *, kind: ReturnKind) -> float | pd.Series:
    """Total return over the whole sample, in the same kind as the input.

    Parameters
    ----------
    returns
        Per-period returns without NaN. An empty input compounds to 0.
    kind
        Return kind of the input and of the result.

    Returns
    -------
    float or Series
        A float for a series; one value per column for a frame.

    Raises
    ------
    ValidationError
        If the input contains NaN.
    """
    _check_kind(kind)
    if isinstance(returns, pd.Series):
        values = validate_series(returns, nan_policy=NanPolicy.RAISE, name="returns").to_numpy()
        if kind is ReturnKind.SIMPLE:
            return float(np.prod(1.0 + values) - 1.0)
        return float(np.sum(values))
    frame = validate_frame(returns, nan_policy=NanPolicy.RAISE, name="returns")
    if kind is ReturnKind.SIMPLE:
        return (1.0 + frame).prod() - 1.0
    return frame.sum()


def wealth_index(returns: _T, *, kind: ReturnKind, initial: float) -> _T:
    """Value of an investment of ``initial`` after each period's return.

    The output has the same index as ``returns``: the value at ``t`` includes the return of
    period ``t``. The starting value itself is not included.

    Raises
    ------
    ValidationError
        If ``initial`` is not a positive finite number or the returns contain NaN.
    """
    _check_kind(kind)
    if not (math.isfinite(initial) and initial > 0):
        raise ValidationError(f"initial must be a positive finite number, got {initial!r}")
    valid = _validate(returns, NanPolicy.RAISE, "returns")
    if kind is ReturnKind.SIMPLE:
        return initial * (1.0 + valid).cumprod()
    return initial * _ufunc(np.exp, valid.cumsum())


def aggregate_returns(
    returns: _T, *, kind: ReturnKind, to: Frequency, min_periods: int
) -> AggregatedReturns[_T]:
    """Compound returns within calendar buckets of a lower frequency.

    Parameters
    ----------
    returns
        Per-period returns on a validated index. NaNs are allowed.
    kind
        Return kind of input and output. Simple returns compound multiplicatively, log returns
        add.
    to
        Target frequency. Buckets are labelled by period end (e.g. ``2026-01-31`` for January).
    min_periods
        Minimum number of observations a bucket needs. Buckets with fewer, including empty
        buckets in gaps, are NaN rather than dropped, so partial first and last periods remain
        visible.

    Returns
    -------
    AggregatedReturns
        Aggregated returns and the observation count of every bucket. A bucket containing a
        NaN is NaN (per column for frames): a missing return is never treated as zero.
    """
    _check_kind(kind)
    if not isinstance(to, Frequency):
        raise ValidationError(f"to must be a Frequency, got {to!r}")
    if not _is_positive_int(min_periods):
        raise ValidationError(f"min_periods must be a positive integer, got {min_periods!r}")
    valid = _validate(returns, NanPolicy.KEEP, "returns")
    frame = _as_frame(valid)
    rule = to.value

    counts = pd.Series(1, index=frame.index, dtype="int64").resample(rule).sum()
    has_nan = frame.isna().resample(rule).sum() > 0
    if kind is ReturnKind.SIMPLE:
        aggregated = (1.0 + frame).resample(rule).prod() - 1.0
    else:
        aggregated = frame.resample(rule).sum()
    too_few = (counts < min_periods).to_numpy()[:, np.newaxis]
    invalid = pd.DataFrame(
        has_nan.to_numpy() | too_few, index=aggregated.index, columns=aggregated.columns
    )
    return AggregatedReturns(returns=_restore(aggregated.mask(invalid), like=valid), counts=counts)


# --------------------------------------------------------------------------- helpers
def _as_frame(obj: pd.Series | pd.DataFrame) -> pd.DataFrame:
    if isinstance(obj, pd.Series):
        return obj.to_frame()
    return obj


def _restore(frame: pd.DataFrame, like: _T) -> _T:
    """Convert a frame computed by :func:`_as_frame` back to the type of ``like``."""
    if isinstance(like, pd.Series):
        series = frame.iloc[:, 0]
        series.name = like.name
        return series
    return frame


def _ufunc(func: np.ufunc, obj: _T) -> _T:
    """Apply a NumPy ufunc element-wise, keeping the pandas type, index and labels."""
    return cast(_T, func(obj))


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value >= 1


def _check_kind(kind: object) -> None:
    if not isinstance(kind, ReturnKind):
        raise ValidationError(f"kind must be a ReturnKind, got {kind!r}")


def _validate(obj: _T, nan_policy: NanPolicy, name: str) -> _T:
    if isinstance(obj, pd.DataFrame):
        return validate_frame(obj, nan_policy=nan_policy, name=name)
    return validate_series(obj, nan_policy=nan_policy, name=name)
