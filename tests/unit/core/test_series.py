"""Validation of time-indexed pandas objects.

A validated object has a strictly increasing ``DatetimeIndex`` and finite-or-NaN ``float64``
values; NaNs are handled by an explicit policy. Nothing is sorted, filled or aligned silently.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import AlignmentError, ValidationError
from qrlab.core.series import NanPolicy, require_same_index, validate_frame, validate_series


def _idx(*days: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(list(days))


def _series(values: list[float], days: tuple[str, ...] | None = None) -> pd.Series:
    if days is None:
        days = tuple(f"2026-01-{d:02d}" for d in range(5, 5 + len(values)))
    return pd.Series(values, index=_idx(*days), name="x")


# --------------------------------------------------------------------------- happy path
def test_valid_series_is_returned_as_float64_copy() -> None:
    s = pd.Series([1, 2, 3], index=_idx("2026-01-05", "2026-01-06", "2026-01-07"), name="p")
    out = validate_series(s, nan_policy=NanPolicy.RAISE)
    assert out.dtype == np.float64
    assert out.name == "p"
    pd.testing.assert_index_equal(out.index, s.index)
    assert out.tolist() == [1.0, 2.0, 3.0]
    out.iloc[0] = 99.0
    assert s.iloc[0] == 1  # the input is never modified, and the output is not a view


def test_input_is_not_mutated() -> None:
    s = _series([1.0, np.nan, 3.0])
    before = s.copy()
    validate_series(s, nan_policy=NanPolicy.DROP)
    pd.testing.assert_series_equal(s, before)


def test_empty_series_is_valid() -> None:
    s = pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    out = validate_series(s, nan_policy=NanPolicy.RAISE)
    assert out.empty
    assert out.dtype == np.float64


def test_single_observation_is_valid() -> None:
    out = validate_series(_series([1.5]), nan_policy=NanPolicy.RAISE)
    assert out.tolist() == [1.5]


def test_tz_aware_index_is_valid() -> None:
    s = _series([1.0, 2.0]).tz_localize("Europe/Rome")
    out = validate_series(s, nan_policy=NanPolicy.RAISE)
    assert isinstance(out.index, pd.DatetimeIndex)
    assert str(out.index.tz) == "Europe/Rome"


def test_nullable_integer_with_missing_value_becomes_nan() -> None:
    s = pd.Series(pd.array([1, None, 3], dtype="Int64"), index=_series([0, 0, 0]).index)
    out = validate_series(s, nan_policy=NanPolicy.KEEP)
    assert out.dtype == np.float64
    assert np.isnan(out.iloc[1])


# --------------------------------------------------------------------------- NaN policy
def test_nan_policy_raise() -> None:
    with pytest.raises(ValidationError, match="NaN"):
        validate_series(_series([1.0, np.nan]), nan_policy=NanPolicy.RAISE)


def test_nan_policy_drop() -> None:
    out = validate_series(_series([1.0, np.nan, 3.0]), nan_policy=NanPolicy.DROP)
    assert out.tolist() == [1.0, 3.0]
    assert list(out.index) == list(_idx("2026-01-05", "2026-01-07"))


def test_nan_policy_keep() -> None:
    out = validate_series(_series([1.0, np.nan]), nan_policy=NanPolicy.KEEP)
    assert np.isnan(out.iloc[1])


def test_all_nan_under_each_policy() -> None:
    s = _series([np.nan, np.nan])
    with pytest.raises(ValidationError):
        validate_series(s, nan_policy=NanPolicy.RAISE)
    assert validate_series(s, nan_policy=NanPolicy.DROP).empty
    assert validate_series(s, nan_policy=NanPolicy.KEEP).isna().all()


def test_nan_policy_must_be_enum() -> None:
    with pytest.raises(ValidationError, match="NanPolicy"):
        validate_series(_series([1.0]), nan_policy="drop")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- invalid index
def test_unsorted_index_raises() -> None:
    s = _series([1.0, 2.0], days=("2026-01-06", "2026-01-05"))
    with pytest.raises(ValidationError, match="increasing"):
        validate_series(s, nan_policy=NanPolicy.RAISE)


def test_duplicated_index_raises() -> None:
    s = _series([1.0, 2.0], days=("2026-01-05", "2026-01-05"))
    with pytest.raises(ValidationError, match="duplicated"):
        validate_series(s, nan_policy=NanPolicy.RAISE)


def test_non_datetime_index_raises() -> None:
    with pytest.raises(ValidationError, match="DatetimeIndex"):
        validate_series(pd.Series([1.0, 2.0]), nan_policy=NanPolicy.RAISE)


def test_nat_in_index_raises() -> None:
    s = pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2026-01-05", pd.NaT]))
    with pytest.raises(ValidationError, match="NaT"):
        validate_series(s, nan_policy=NanPolicy.RAISE)


# --------------------------------------------------------------------------- invalid values
@pytest.mark.parametrize("bad", [np.inf, -np.inf])
def test_infinite_values_raise(bad: float) -> None:
    with pytest.raises(ValidationError, match="infinite"):
        validate_series(_series([1.0, bad]), nan_policy=NanPolicy.KEEP)


@pytest.mark.parametrize(
    "values",
    [[True, False], ["a", "b"], [1 + 1j, 2 + 0j]],
    ids=["bool", "object", "complex"],
)
def test_non_real_numeric_dtypes_raise(values: list[object]) -> None:
    s = pd.Series(values, index=_idx("2026-01-05", "2026-01-06"))
    with pytest.raises(ValidationError, match="dtype"):
        validate_series(s, nan_policy=NanPolicy.RAISE)


def test_wrong_type_raises() -> None:
    with pytest.raises(ValidationError, match="Series"):
        validate_series(pd.DataFrame({"a": [1.0]}), nan_policy=NanPolicy.RAISE)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- frames
def _frame() -> pd.DataFrame:
    idx = _idx("2026-01-05", "2026-01-06", "2026-01-07")
    return pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": [1, 2, 3]}, index=idx)


def test_frame_drop_removes_rows_with_any_nan() -> None:
    out = validate_frame(_frame(), nan_policy=NanPolicy.DROP)
    assert list(out.index) == list(_idx("2026-01-05", "2026-01-07"))
    assert (out.dtypes == np.float64).all()


def test_frame_keep_and_raise() -> None:
    assert validate_frame(_frame(), nan_policy=NanPolicy.KEEP).shape == (3, 2)
    with pytest.raises(ValidationError, match="NaN"):
        validate_frame(_frame(), nan_policy=NanPolicy.RAISE)


def test_frame_input_not_mutated() -> None:
    f = _frame()
    before = f.copy()
    validate_frame(f, nan_policy=NanPolicy.DROP)
    pd.testing.assert_frame_equal(f, before)


def test_frame_duplicated_columns_raise() -> None:
    f = pd.DataFrame([[1.0, 2.0]], index=_idx("2026-01-05"), columns=["a", "a"])
    with pytest.raises(ValidationError, match="column"):
        validate_frame(f, nan_policy=NanPolicy.RAISE)


def test_frame_non_numeric_column_raises() -> None:
    f = pd.DataFrame({"a": [1.0], "b": ["x"]}, index=_idx("2026-01-05"))
    with pytest.raises(ValidationError, match="dtype"):
        validate_frame(f, nan_policy=NanPolicy.RAISE)


def test_frame_unsorted_index_raises() -> None:
    f = pd.DataFrame({"a": [1.0, 2.0]}, index=_idx("2026-01-06", "2026-01-05"))
    with pytest.raises(ValidationError, match="increasing"):
        validate_frame(f, nan_policy=NanPolicy.RAISE)


def test_empty_frame_is_valid() -> None:
    f = pd.DataFrame({"a": pd.Series([], dtype=float)}, index=pd.DatetimeIndex([]))
    assert validate_frame(f, nan_policy=NanPolicy.RAISE).empty


# --------------------------------------------------------------------------- alignment
def test_same_index_passes() -> None:
    a = _series([1.0, 2.0])
    require_same_index(a, a * 2, a.to_frame())


def test_different_index_raises() -> None:
    a = _series([1.0, 2.0])
    b = _series([1.0, 2.0], days=("2026-01-05", "2026-01-07"))
    with pytest.raises(AlignmentError):
        require_same_index(a, b)


def test_tz_mismatch_raises_even_for_same_instants() -> None:
    a = _series([1.0, 2.0]).tz_localize("UTC")
    b = a.tz_convert("Europe/Rome")
    with pytest.raises(AlignmentError, match="time zone"):
        require_same_index(a, b)


def test_naive_vs_aware_raises() -> None:
    a = _series([1.0, 2.0])
    with pytest.raises(AlignmentError):
        require_same_index(a, a.tz_localize("UTC"))


def test_require_same_index_with_fewer_than_two_objects() -> None:
    require_same_index()
    require_same_index(_series([1.0]))
