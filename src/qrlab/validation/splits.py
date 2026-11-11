r"""Walk-forward splits with purging and embargo.

Splits are positions in a sorted, unique ``DatetimeIndex``. Test windows move forward and never
overlap. The rule, checked on every split: every training observation, **including the end of
its label**, is strictly before the first test observation,
:math:`\max(\text{train label end}) < \min(\text{test time})`.

- **Expanding:** train :math:`[0, s)` with :math:`s` starting at ``min_train`` and growing by
  ``step``.
- **Rolling:** train :math:`[s - \text{train\_size}, s)`.
- **Embargo:** test :math:`[s + e, s + e + \text{test\_size})`, skipping ``embargo`` positions.
- **Purging** (Lopez de Prado 2018, ch. 7): training observations whose label end is on or after
  the first test time are removed. Without label ends, a label is known at its own time.

A split is produced only if its whole test window fits; unused trailing observations are
reported. ``step`` must be at least ``test_size``, so test windows never overlap. Random or
shuffled splits are deliberately not provided.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, require_same_index, validate_series

__all__ = ["Split", "Splits", "expanding_splits", "rolling_splits", "take"]


@dataclass(frozen=True)
class Split:
    """One train/test split as positions, with its dates.

    Raises on construction if any training label ends on or after the first test time.
    """

    train: np.ndarray
    test: np.ndarray
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    purged: int
    last_label_end: date

    def __post_init__(self) -> None:
        """Check the no-leakage rule."""
        if self.train.size == 0 or self.test.size == 0:
            raise ValidationError("a split needs training and test observations")
        if not self.last_label_end < self.test_start:
            raise ValidationError(
                f"leakage: a training label ends on {self.last_label_end}, test starts on "
                f"{self.test_start}"
            )
        if np.intersect1d(self.train, self.test).size:
            raise ValidationError("train and test positions overlap")


@dataclass(frozen=True)
class Splits:
    """All splits of an index, with the parameters used."""

    index: pd.DatetimeIndex
    splits: tuple[Split, ...]
    kind: str
    params: dict[str, int]
    unused: int

    def __len__(self) -> int:
        """Return the number of splits."""
        return len(self.splits)


def expanding_splits(
    index: pd.DatetimeIndex,
    *,
    min_train: int,
    test_size: int,
    step: int,
    embargo: int,
    label_ends: pd.Series | None,
) -> Splits:
    """Return expanding-window walk-forward splits."""
    _positive("min_train", min_train)
    params = {"min_train": min_train, "test_size": test_size, "step": step, "embargo": embargo}
    return _build(index, "expanding", None, min_train, test_size, step, embargo, label_ends, params)


def rolling_splits(
    index: pd.DatetimeIndex,
    *,
    train_size: int,
    test_size: int,
    step: int,
    embargo: int,
    label_ends: pd.Series | None,
) -> Splits:
    """Return rolling-window walk-forward splits of ``train_size`` observations."""
    _positive("train_size", train_size)
    params = {"train_size": train_size, "test_size": test_size, "step": step, "embargo": embargo}
    return _build(
        index, "rolling", train_size, train_size, test_size, step, embargo, label_ends, params
    )


def take(
    data: pd.Series | pd.DataFrame, splits: Splits, positions: np.ndarray
) -> pd.Series | pd.DataFrame:
    """Select rows of ``data`` by position, after checking it is on the splits' index."""
    if not data.index.equals(splits.index):
        raise ValidationError("data is not on the index the splits were built on")
    return data.iloc[positions]


def _build(
    index: pd.DatetimeIndex,
    kind: str,
    window: int | None,
    first: int,
    test_size: int,
    step: int,
    embargo: int,
    label_ends: pd.Series | None,
    params: dict[str, int],
) -> Splits:
    _positive("test_size", test_size)
    _positive("step", step)
    if step < test_size:
        raise ValidationError(f"step {step} < test_size {test_size}: test windows would overlap")
    if type(embargo) is not int or embargo < 0:
        raise ValidationError(f"embargo must be an int >= 0, got {embargo!r}")
    if not isinstance(index, pd.DatetimeIndex):
        raise ValidationError("index must be a pandas DatetimeIndex")
    validate_series(pd.Series(0.0, index=index), nan_policy=NanPolicy.RAISE, name="index")
    ends = _label_ends(index, label_ends)
    n = len(index)
    if first + embargo + test_size > n:
        raise ValidationError(
            f"{n} observations are fewer than {first} train + {embargo} embargo + {test_size} test"
        )
    splits: list[Split] = []
    end_of_last_test = 0
    start = first
    while start + embargo + test_size <= n:
        test = np.arange(start + embargo, start + embargo + test_size)
        candidates = np.arange(start - window if window is not None else 0, start)
        test_time = index[test[0]]
        keep = candidates[ends[candidates] < test_time]
        if keep.size == 0:
            when = test_time.date()
            raise ValidationError(f"purging removes every training observation before {when}")
        splits.append(
            Split(
                train=keep,
                test=test,
                train_start=index[keep[0]].date(),
                train_end=index[keep[-1]].date(),
                test_start=test_time.date(),
                test_end=index[test[-1]].date(),
                purged=int(candidates.size - keep.size),
                last_label_end=pd.Timestamp(ends[keep].max()).date(),
            )
        )
        end_of_last_test = int(test[-1]) + 1
        start += step
    return Splits(index, tuple(splits), kind, params, n - end_of_last_test)


def _label_ends(index: pd.DatetimeIndex, label_ends: pd.Series | None) -> np.ndarray:
    if label_ends is None:
        return index.to_numpy()
    if not isinstance(label_ends, pd.Series):
        raise ValidationError("label_ends must be a pandas Series or None")
    require_same_index(pd.Series(0.0, index=index), label_ends)
    values = pd.DatetimeIndex(label_ends)
    if values.hasnans:
        raise ValidationError("label_ends must not contain missing values")
    if (values < index).any():
        raise ValidationError("a label ends before its own observation time")
    return values.to_numpy()


def _positive(name: str, value: object) -> None:
    if type(value) is not int or value < 1:
        raise ValidationError(f"{name} must be a positive int, got {value!r}")
