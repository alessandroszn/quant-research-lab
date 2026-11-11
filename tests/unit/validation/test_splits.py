"""Walk-forward splits, purging and embargo (hand examples from design note 4.1).

- 10 dates, expanding, min_train 4, test 2, step 2: train [0-3] test [4-5]; [0-5] [6-7];
  [0-7] [8-9]; unused 0. With embargo 1: tests [5-6] and [7-8]; unused 1.
- 10 dates, rolling, train 3, test 2, step 3: train [0-2] test [3-4]; [3-5] [6-7]; unused 2.
- 12 months, labels ending 3 months later, expanding min_train 6, test 3, step 3: the first
  split purges positions 3, 4, 5 (labels end at 6, 7, 8): train [0-2], purged 3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import AlignmentError, ValidationError
from qrlab.validation import Split, expanding_splits, rolling_splits, take

TEN = pd.date_range("2020-01-31", periods=10, freq="ME")


def _ranges(splits: object) -> list[tuple[list[int], list[int]]]:
    return [(s.train.tolist(), s.test.tolist()) for s in splits.splits]  # type: ignore[attr-defined]


def test_expanding_hand_example() -> None:
    result = expanding_splits(TEN, min_train=4, test_size=2, step=2, embargo=0, label_ends=None)
    assert _ranges(result) == [
        ([0, 1, 2, 3], [4, 5]),
        ([0, 1, 2, 3, 4, 5], [6, 7]),
        ([0, 1, 2, 3, 4, 5, 6, 7], [8, 9]),
    ]
    assert (len(result), result.unused, result.kind) == (3, 0, "expanding")
    first = result.splits[0]
    assert (first.train_start, first.train_end) == (TEN[0].date(), TEN[3].date())
    assert (first.test_start, first.test_end, first.purged) == (TEN[4].date(), TEN[5].date(), 0)
    assert result.params == {"min_train": 4, "test_size": 2, "step": 2, "embargo": 0}


def test_embargo_hand_example() -> None:
    result = expanding_splits(TEN, min_train=4, test_size=2, step=2, embargo=1, label_ends=None)
    assert [s.test.tolist() for s in result.splits] == [[5, 6], [7, 8]]
    assert [s.train.tolist()[-1] for s in result.splits] == [3, 5]
    assert result.unused == 1


def test_rolling_hand_example() -> None:
    result = rolling_splits(TEN, train_size=3, test_size=2, step=3, embargo=0, label_ends=None)
    assert _ranges(result) == [([0, 1, 2], [3, 4]), ([3, 4, 5], [6, 7])]
    assert result.unused == 2
    assert result.params["train_size"] == 3


def test_purging_hand_example() -> None:
    months = pd.date_range("2020-01-31", periods=12, freq="ME")
    ends = pd.Series(months + pd.offsets.MonthEnd(3), index=months)
    result = expanding_splits(months, min_train=6, test_size=3, step=3, embargo=0, label_ends=ends)
    first = result.splits[0]
    assert first.train.tolist() == [0, 1, 2]
    assert first.purged == 3
    assert first.last_label_end == months[5].date()
    assert first.last_label_end < first.test_start
    second = result.splits[1]
    assert second.train.tolist() == [0, 1, 2, 3, 4, 5]  # 6, 7, 8 purged: labels end at 9-11
    assert second.purged == 3


@pytest.mark.parametrize("config", range(500))
def test_no_training_label_reaches_the_test_window(config: int) -> None:
    rng = np.random.default_rng(config)
    n = int(rng.integers(8, 80))
    index = pd.date_range("2010-01-01", periods=n, freq="D")
    horizons = rng.integers(0, 6, size=n)
    ends = pd.Series(index + pd.to_timedelta(horizons, unit="D"), index=index)
    test_size, extra, embargo = (int(v) for v in rng.integers(1, 6, size=3))
    step = test_size + extra - 1  # step >= test_size: test windows never overlap
    first = int(rng.integers(1, max(2, n // 3)))
    label_ends = ends if rng.random() < 0.7 else None
    try:
        if rng.random() < 0.5:
            result = expanding_splits(
                index,
                min_train=first,
                test_size=test_size,
                step=step,
                embargo=embargo - 1,
                label_ends=label_ends,
            )
        else:
            result = rolling_splits(
                index,
                train_size=first,
                test_size=test_size,
                step=step,
                embargo=embargo - 1,
                label_ends=label_ends,
            )
    except ValidationError:
        return  # too little data, or purging emptied a training set: refused, never leaked
    effective = ends if label_ends is not None else pd.Series(index, index=index)
    previous_test_end = -1
    for split in result.splits:
        assert effective.iloc[split.train].max() < index[split.test[0]]
        assert split.train.max() < split.test.min()
        assert split.test.min() > previous_test_end  # test windows move forward, no overlap
        previous_test_end = int(split.test.max())
        assert len(split.test) == test_size


def test_take_checks_the_index() -> None:
    result = expanding_splits(TEN, min_train=4, test_size=2, step=2, embargo=0, label_ends=None)
    data = pd.Series(np.arange(10.0), index=TEN)
    split = result.splits[0]
    assert np.asarray(take(data, result, split.test)).tolist() == [4.0, 5.0]
    with pytest.raises(ValidationError, match="index"):
        take(data.iloc[1:], result, split.test)


def test_errors() -> None:
    with pytest.raises(ValidationError, match="fewer than"):
        expanding_splits(TEN, min_train=8, test_size=2, step=2, embargo=1, label_ends=None)
    for name in ("min_train", "test_size", "step"):
        kwargs = {"min_train": 4, "test_size": 2, "step": 2, name: 0}
        with pytest.raises(ValidationError, match=name):
            expanding_splits(TEN, embargo=0, label_ends=None, **kwargs)
    with pytest.raises(ValidationError, match="train_size"):
        rolling_splits(TEN, train_size=1.5, test_size=1, step=1, embargo=0, label_ends=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="overlap"):
        expanding_splits(TEN, min_train=4, test_size=3, step=2, embargo=0, label_ends=None)
    with pytest.raises(ValidationError, match="embargo"):
        expanding_splits(TEN, min_train=4, test_size=2, step=2, embargo=-1, label_ends=None)
    with pytest.raises(ValidationError, match="DatetimeIndex"):
        expanding_splits(
            pd.Index(range(10)),  # type: ignore[arg-type]
            min_train=4,
            test_size=2,
            step=2,
            embargo=0,
            label_ends=None,
        )
    with pytest.raises(ValidationError):
        expanding_splits(TEN[::-1], min_train=4, test_size=2, step=2, embargo=0, label_ends=None)


def test_label_end_errors() -> None:
    early = pd.Series(TEN - pd.Timedelta(days=1), index=TEN)
    with pytest.raises(ValidationError, match="before its own"):
        expanding_splits(TEN, min_train=4, test_size=2, step=2, embargo=0, label_ends=early)
    with pytest.raises(AlignmentError):
        expanding_splits(
            TEN,
            min_train=4,
            test_size=2,
            step=2,
            embargo=0,
            label_ends=pd.Series(TEN[1:], index=TEN[1:]),
        )
    gappy = pd.Series(TEN, index=TEN).astype(object)
    gappy.iloc[2] = None
    with pytest.raises(ValidationError, match="missing"):
        expanding_splits(TEN, min_train=4, test_size=2, step=2, embargo=0, label_ends=gappy)
    with pytest.raises(ValidationError, match="Series"):
        expanding_splits(TEN, min_train=4, test_size=2, step=2, embargo=0, label_ends=list(TEN))  # type: ignore[arg-type]
    far = pd.Series(TEN + pd.offsets.MonthEnd(20), index=TEN)
    with pytest.raises(ValidationError, match="purging removes every"):
        expanding_splits(TEN, min_train=4, test_size=2, step=2, embargo=0, label_ends=far)


def test_split_rejects_leakage_directly() -> None:
    day = TEN[4].date()
    with pytest.raises(ValidationError, match="leakage"):
        Split(np.array([0]), np.array([1]), day, day, day, day, 0, day)
    with pytest.raises(ValidationError, match="overlap"):
        Split(
            np.array([0, 1]),
            np.array([1]),
            TEN[0].date(),
            TEN[1].date(),
            TEN[1].date(),
            TEN[1].date(),
            0,
            TEN[0].date(),
        )
    with pytest.raises(ValidationError, match="needs training"):
        Split(np.array([], dtype=int), np.array([1]), day, day, day, day, 0, day)
