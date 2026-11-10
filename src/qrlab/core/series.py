"""Validation of time-indexed pandas objects.

A *validated* series or frame has

- a :class:`pandas.DatetimeIndex` without ``NaT``;
- a strictly increasing index (sorted, no duplicated timestamps);
- real numeric values cast to ``float64``, with no ``+inf`` or ``-inf``;
- missing values handled according to an explicit :class:`NanPolicy`.

Nothing is sorted, filled, aligned or dropped silently. An unsorted or duplicated index raises,
because a duplicated timestamp usually signals a data error that sorting would hide.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypeVar

import numpy as np
import pandas as pd
from pandas.api.extensions import ExtensionDtype
from pandas.api.types import is_bool_dtype, is_float_dtype, is_integer_dtype

from qrlab.core.errors import AlignmentError, ValidationError

__all__ = ["NanPolicy", "require_same_index", "validate_frame", "validate_series"]

_T = TypeVar("_T", pd.Series, pd.DataFrame)


class NanPolicy(Enum):
    """How missing values are treated during validation.

    Attributes
    ----------
    RAISE
        Any NaN raises :class:`~qrlab.core.errors.ValidationError`.
    DROP
        Rows containing a NaN are removed (for frames: a NaN in *any* column).
    KEEP
        NaNs are kept; downstream functions must handle them explicitly.
    """

    RAISE = "raise"
    DROP = "drop"
    KEEP = "keep"


def validate_series(obj: pd.Series, *, nan_policy: NanPolicy, name: str = "series") -> pd.Series:
    """Return a validated ``float64`` copy of a time-indexed series.

    Parameters
    ----------
    obj
        Series indexed by a :class:`pandas.DatetimeIndex`.
    nan_policy
        Treatment of missing values; see :class:`NanPolicy`.
    name
        Label used in error messages.

    Returns
    -------
    pandas.Series
        A new ``float64`` series; the input is not modified.

    Raises
    ------
    ValidationError
        If the object is not a series, its index is not a strictly increasing
        ``DatetimeIndex`` without ``NaT``, its dtype is not real numeric, it contains infinite
        values, or it contains NaN under ``NanPolicy.RAISE``.
    """
    if not isinstance(obj, pd.Series):
        raise ValidationError(f"{name}: expected a pandas Series, got {type(obj).__name__}")
    _check_nan_policy(nan_policy)
    _check_index(obj.index, name)
    _check_dtype(obj.dtype, name)
    out = obj.astype("float64")
    _check_finite(out.to_numpy(), name)
    return _apply_nan_policy(out, nan_policy, name)


def validate_frame(
    obj: pd.DataFrame, *, nan_policy: NanPolicy, name: str = "frame"
) -> pd.DataFrame:
    """Return a validated ``float64`` copy of a time-indexed frame.

    Parameters
    ----------
    obj
        Frame indexed by a :class:`pandas.DatetimeIndex`, with unique column labels.
    nan_policy
        Treatment of missing values. ``NanPolicy.DROP`` removes a row if *any* column is NaN.
    name
        Label used in error messages.

    Returns
    -------
    pandas.DataFrame
        A new frame with every column ``float64``; the input is not modified.

    Raises
    ------
    ValidationError
        As :func:`validate_series`, and also for duplicated column labels.
    """
    if not isinstance(obj, pd.DataFrame):
        raise ValidationError(f"{name}: expected a pandas DataFrame, got {type(obj).__name__}")
    _check_nan_policy(nan_policy)
    _check_index(obj.index, name)
    if obj.columns.has_duplicates:
        dupes = sorted({str(c) for c in obj.columns[obj.columns.duplicated()]})
        raise ValidationError(f"{name}: duplicated column labels {dupes}")
    for column, dtype in obj.dtypes.items():
        _check_dtype(dtype, f"{name}[{column!r}]")
    out = obj.astype("float64")
    _check_finite(out.to_numpy(), name)
    return _apply_nan_policy(out, nan_policy, name)


def require_same_index(*objs: pd.Series | pd.DataFrame) -> None:
    """Raise unless all objects share exactly the same index and time zone.

    Indexes are compared element by element. Two indexes that represent the same instants in
    different time zones are considered different, because combining them would silently mix
    conventions.

    Parameters
    ----------
    *objs
        Series or frames to compare. Fewer than two objects always pass.

    Raises
    ------
    AlignmentError
        If any index differs from the first one.
    """
    if len(objs) < 2:
        return
    first = objs[0].index
    for position, other in enumerate(objs[1:], start=1):
        index = other.index
        first_tz = getattr(first, "tz", None)
        other_tz = getattr(index, "tz", None)
        if str(first_tz) != str(other_tz):
            raise AlignmentError(
                f"object {position} has time zone {other_tz}, object 0 has {first_tz}"
            )
        if not first.equals(index):
            raise AlignmentError(
                f"object {position} has a different index from object 0 "
                f"({len(index)} vs {len(first)} labels); align explicitly before combining"
            )


# --------------------------------------------------------------------------- helpers
def _check_nan_policy(nan_policy: object) -> None:
    if not isinstance(nan_policy, NanPolicy):
        raise ValidationError(f"nan_policy must be a NanPolicy, got {nan_policy!r}")


def _check_index(index: pd.Index, name: str) -> None:
    if not isinstance(index, pd.DatetimeIndex):
        raise ValidationError(f"{name}: index must be a DatetimeIndex, got {type(index).__name__}")
    if index.hasnans:
        raise ValidationError(f"{name}: index contains NaT")
    if index.has_duplicates:
        dupes = index[index.duplicated()].unique()[:5]
        raise ValidationError(f"{name}: duplicated timestamps in index, e.g. {list(dupes)}")
    if not index.is_monotonic_increasing:
        raise ValidationError(f"{name}: index must be strictly increasing; sort it explicitly")


def _check_dtype(dtype: np.dtype[Any] | ExtensionDtype, name: str) -> None:
    if is_bool_dtype(dtype) or not (is_float_dtype(dtype) or is_integer_dtype(dtype)):
        raise ValidationError(f"{name}: dtype {dtype} is not a real numeric dtype")


def _check_finite(values: np.ndarray[Any, np.dtype[np.floating[Any]]], name: str) -> None:
    if np.isinf(values).any():
        raise ValidationError(f"{name}: contains infinite values")


def _rows_with_nan(obj: pd.Series | pd.DataFrame) -> pd.Series:
    """Boolean series: True where the row contains at least one NaN."""
    if isinstance(obj, pd.DataFrame):
        return obj.isna().any(axis=1)
    return obj.isna()


def _apply_nan_policy(obj: _T, nan_policy: NanPolicy, name: str) -> _T:
    if nan_policy is NanPolicy.KEEP:
        return obj
    has_nan = _rows_with_nan(obj)
    if nan_policy is NanPolicy.RAISE:
        count = int(has_nan.sum())
        if count:
            raise ValidationError(f"{name}: {count} row(s) contain NaN under NanPolicy.RAISE")
        return obj
    return obj.loc[~has_nan.to_numpy()]
