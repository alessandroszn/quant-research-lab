"""Which output tables can be drawn as a chart, and what the chart's readout says (12.3b).

Qt-free. A table is chartable when it is a dated time series as written by the runner: its
index is all ISO dates (``YYYY-MM-DD``), strictly increasing, it has at least two rows and at
least one numeric column. The check is on the index's text, so row numbers are never taken
for dates.

Nothing is computed: the chart draws each numeric column's values as they are in the file.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from qrlab_app.display import cell_text, date_text

__all__ = ["MAX_LINES", "ChartModel"]

MAX_LINES = 8
"""Lines shown when a chart first opens; the others are one tick box away."""

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class ChartModel:
    """A dated table's numeric columns, ready to draw.

    Build it with :meth:`from_frame`, which returns ``None`` for a table that is not a dated
    time series.
    """

    dates: tuple[date, ...]
    columns: tuple[str, ...]
    series: dict[str, tuple[float, ...]]

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> ChartModel | None:
        """Return the chart of ``frame``, or ``None`` when it cannot be drawn as one."""
        if len(frame) < 2:
            return None
        texts = [str(value) for value in frame.index]
        if not all(_ISO_DATE.fullmatch(text) for text in texts):
            return None
        try:
            dates = tuple(date.fromisoformat(text) for text in texts)
        except ValueError:  # 2026-02-30 looks like a date but is not one
            return None
        if any(later <= earlier for earlier, later in itertools.pairwise(dates)):
            return None
        columns = tuple(
            str(name)
            for name in frame.columns
            if pd.api.types.is_numeric_dtype(frame[name])
            and not pd.api.types.is_bool_dtype(frame[name])
        )
        if not columns:
            return None
        series = {
            str(name): tuple(float(v) for v in frame[name])
            for name in frame.columns
            if str(name) in columns
        }
        return cls(dates, columns, series)

    @property
    def shown_at_first(self) -> tuple[str, ...]:
        """Return the columns drawn when the chart opens (at most :data:`MAX_LINES`)."""
        return self.columns[:MAX_LINES]

    def nearest(self, when: date) -> int:
        """Return the position of the date nearest ``when`` (the earlier one on a tie)."""
        gaps = [abs((day - when).days) for day in self.dates]
        return gaps.index(min(gaps))

    def readout(self, position: int, columns: Sequence[str], language: str) -> str:
        """Return the date at ``position`` and each of ``columns``' values, in ``language``."""
        parts = [date_text(self.dates[position], language)]
        for name in columns:
            value = self.series[name][position]
            text = cell_text(value, language)  # NaN shows as the app's missing mark
            parts.append(f"{name}: {text}")
        return "  ·  ".join(parts)
