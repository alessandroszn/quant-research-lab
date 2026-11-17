"""Which tables are charts, and the chart's readout (design note 12.3b), without Qt."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
import pytest

from qrlab_app.charts import MAX_LINES, ChartModel


def _frame(index: Sequence[object], **columns: Sequence[object]) -> pd.DataFrame:
    return pd.DataFrame(columns, index=list(index))


DATES = ["2026-01-31", "2026-02-28", "2026-03-31"]


def test_a_dated_table_is_a_chart() -> None:
    frame = _frame(DATES, gross=[100.0, 101.5, 99.0], net=[100.0, 101.0, float("nan")])
    chart = ChartModel.from_frame(frame)
    assert chart is not None
    assert chart.dates == (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31))
    assert chart.columns == ("gross", "net")
    assert chart.series["gross"] == (100.0, 101.5, 99.0)
    assert chart.shown_at_first == ("gross", "net")


@pytest.mark.parametrize(
    ("index", "why"),
    [
        ([0, 1, 2], "row numbers parse as dates in pandas, not here"),
        (["2026-01-31 00:00:00", "2026-02-28 00:00:00", "2026-03-31 00:00:00"], "times"),
        (["2026-02-28", "2026-01-31", "2026-03-31"], "unsorted"),
        (["2026-01-31", "2026-01-31", "2026-03-31"], "duplicated"),
        (["2026-01-31", "2026-02-30", "2026-03-31"], "not a calendar date"),
        (["equity", "bonds", "cash"], "names"),
    ],
)
def test_what_is_not_a_chart(index: Sequence[object], why: str) -> None:
    assert ChartModel.from_frame(_frame(index, x=[1.0, 2.0, 3.0])) is None, why


def test_one_row_or_no_numbers_is_not_a_chart() -> None:
    assert ChartModel.from_frame(_frame(["2026-01-31"], x=[1.0])) is None
    text_only = _frame(DATES, side=["buy", "sell", "buy"], done=[True, False, True])
    assert ChartModel.from_frame(text_only) is None  # text and booleans are not lines
    mixed = _frame(DATES, side=["buy", "sell", "buy"], units=[3, 4, 5], done=[True, True, False])
    chart = ChartModel.from_frame(mixed)
    assert chart is not None
    assert chart.columns == ("units",)


def test_at_most_eight_lines_at_first() -> None:
    columns = {f"asset_{n:02d}": [0.1, 0.1, 0.1] for n in range(11)}
    chart = ChartModel.from_frame(_frame(DATES, **columns))
    assert chart is not None
    assert len(chart.columns) == 11
    assert chart.shown_at_first == tuple(f"asset_{n:02d}" for n in range(MAX_LINES))


def test_the_nearest_date() -> None:
    chart = ChartModel.from_frame(_frame(DATES, x=[1.0, 2.0, 3.0]))
    assert chart is not None
    assert chart.nearest(date(2025, 12, 1)) == 0  # before the first
    assert chart.nearest(date(2027, 1, 1)) == 2  # after the last
    assert chart.nearest(date(2026, 2, 28)) == 1  # on a date
    assert chart.nearest(date(2026, 2, 10)) == 0  # 10 days after Jan 31, 18 before Feb 28
    assert chart.nearest(date(2026, 3, 16)) == 2  # 16 days after Feb 28, 15 before Mar 31
    assert chart.nearest(date(2026, 2, 14)) == 0  # 14 and 14: the earlier date


def test_the_readout_in_both_languages() -> None:
    frame = _frame(DATES, gross=[100000.0, 101.5, 99.0], net=[100.0, 0.0123456789, float("nan")])
    chart = ChartModel.from_frame(frame)
    assert chart is not None
    assert chart.readout(0, ["gross", "net"], "en") == "2026-01-31  ·  gross: 100,000  ·  net: 100"
    assert chart.readout(1, ["gross", "net"], "it") == (
        "28/02/2026  ·  gross: 101,5  ·  net: 0,0123457"
    )
    assert chart.readout(2, ["net"], "en") == "2026-03-31  ·  net: \u2014"  # a gap in the line
    assert chart.readout(2, [], "en") == "2026-03-31"
