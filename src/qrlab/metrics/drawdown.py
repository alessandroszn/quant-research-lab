r"""Drawdowns of a series of simple returns.

The wealth path starts at :math:`W_0 = 1` *before* the first return, so a loss in the first
period is a drawdown. :math:`DD_t = W_t / \max_{s \le t} W_s - 1` for :math:`t = 1..n`.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from qrlab.metrics._inputs import check_periods_per_year, returns_array
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.performance import annualised_geometric_return

__all__ = ["calmar_ratio", "drawdown_episodes", "drawdown_series", "max_drawdown", "ulcer_index"]

EPISODE_COLUMNS = (
    "peak",
    "peak_is_sample_start",
    "trough",
    "recovery",
    "depth",
    "periods_to_trough",
    "periods_to_recovery",
)


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Drawdown after each period (0 at a new high, negative below the running peak)."""
    values = returns_array(returns, name="returns", min_n=1)
    return pd.Series(_drawdowns(values), index=returns.index, name="drawdown")


def max_drawdown(returns: pd.Series) -> float:
    """Most negative drawdown (0 if wealth never fell below a previous peak)."""
    return float(np.min(_drawdowns(returns_array(returns, name="returns", min_n=1))))


def ulcer_index(returns: pd.Series) -> float:
    r"""Ulcer index :math:`\sqrt{\tfrac{1}{n}\sum_t DD_t^2}`, in decimals."""
    dd = _drawdowns(returns_array(returns, name="returns", min_n=1))
    return math.sqrt(float(np.mean(dd**2)))


def calmar_ratio(returns: pd.Series, *, periods_per_year: float) -> float:
    """Compound annual growth rate divided by the absolute maximum drawdown.

    Computed over the whole sample passed in; restrict the series to apply a window such as
    the conventional 36 months.
    """
    check_periods_per_year(periods_per_year)
    worst = max_drawdown(returns)
    if worst == 0.0:
        raise UndefinedMetricError("calmar_ratio: no drawdown in the sample")
    return annualised_geometric_return(returns, periods_per_year=periods_per_year) / abs(worst)


def drawdown_episodes(returns: pd.Series) -> pd.DataFrame:
    """One row per drawdown episode, in chronological order.

    Columns:

    - ``peak``: date of the wealth peak the episode started from; ``NaT`` when the peak is the
      initial wealth before the first return (then ``peak_is_sample_start`` is True);
    - ``trough``: date of the lowest wealth in the episode;
    - ``recovery``: first date wealth is back at or above the peak, ``NaT`` if never;
    - ``depth``: drawdown at the trough (negative);
    - ``periods_to_trough`` and ``periods_to_recovery``: periods counted from the peak
      (``<NA>`` if not recovered).
    """
    values = returns_array(returns, name="returns", min_n=1)
    wealth = np.concatenate([[1.0], np.cumprod(1.0 + values)])
    dates = list(returns.index)
    rows: list[dict[str, object]] = []
    peak_pos = 0
    start: int | None = None
    for t in range(1, len(wealth)):
        if wealth[t] >= wealth[peak_pos]:
            if start is not None:
                rows.append(_episode(wealth, dates, peak_pos, start, t))
                start = None
            peak_pos = t
        elif start is None:
            start = t
    if start is not None:
        rows.append(_episode(wealth, dates, peak_pos, start, None))
    frame = pd.DataFrame(rows, columns=list(EPISODE_COLUMNS))
    for column in ("periods_to_trough", "periods_to_recovery"):
        frame[column] = frame[column].astype("Int64")
    for column in ("peak", "trough", "recovery"):
        frame[column] = pd.to_datetime(frame[column])
    return frame


def _episode(
    wealth: np.ndarray, dates: list[object], peak: int, start: int, recovery: int | None
) -> dict[str, object]:
    end = recovery if recovery is not None else len(wealth)
    trough = start + int(np.argmin(wealth[start:end]))
    return {
        "peak": None if peak == 0 else dates[peak - 1],
        "peak_is_sample_start": peak == 0,
        "trough": dates[trough - 1],
        "recovery": None if recovery is None else dates[recovery - 1],
        "depth": float(wealth[trough] / wealth[peak] - 1.0),
        "periods_to_trough": trough - peak,
        "periods_to_recovery": None if recovery is None else recovery - peak,
    }


def _drawdowns(values: np.ndarray) -> np.ndarray:
    wealth = np.concatenate([[1.0], np.cumprod(1.0 + values)])
    peaks = np.maximum.accumulate(wealth)
    return (wealth / peaks - 1.0)[1:]
