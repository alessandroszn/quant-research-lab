"""Deterministic report figures as PNG bytes.

Figures use Matplotlib's object-oriented API with the Agg canvas directly, so no pyplot global
state (and no interactive backend) is ever touched. Output is byte-identical for identical
inputs: fixed size, DPI and font, and the PNG "Software" metadata is removed.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import date
from enum import Enum
from typing import Any

import matplotlib as mpl
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.dates import date2num
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, validate_series
from qrlab.reporting.formatting import NumberStyle, format_number, format_percent

__all__ = ["AxisFormat", "line_figure"]

WIDTH_INCHES, HEIGHT_INCHES, DPI = 8.0, 3.6, 100
_RC: dict[Any, Any] = {
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
}


class AxisFormat(Enum):
    """How y-axis ticks are labelled."""

    NUMBER = "number"
    PERCENT = "percent"


def line_figure(
    lines: Sequence[tuple[str, pd.Series]],
    *,
    title: str,
    y_label: str,
    axis: AxisFormat,
    style: NumberStyle,
    markers: Sequence[date] = (),
    marker_label: str = "",
) -> bytes:
    """Draw one or more dated series as lines and return PNG bytes.

    Parameters
    ----------
    lines
        ``(label, series)`` pairs; series are validated time series without NaN.
    title, y_label
        Text shown on the figure.
    axis
        Tick format of the y axis, using ``style`` for separators.
    markers
        Dates marked with vertical dotted lines (e.g. external flows).
    marker_label
        Legend entry for the markers.
    """
    if not lines:
        raise ValidationError("a figure needs at least one line")
    if not isinstance(axis, AxisFormat):
        raise ValidationError(f"axis must be an AxisFormat, got {axis!r}")
    validated = [
        (name, validate_series(series, nan_policy=NanPolicy.RAISE, name=name))
        for name, series in lines
    ]
    with mpl.rc_context(_RC):
        figure = Figure(figsize=(WIDTH_INCHES, HEIGHT_INCHES), dpi=DPI)
        FigureCanvasAgg(figure)
        ax = figure.add_subplot()
        for name, series in validated:
            ax.plot(series.index, series.to_numpy(), label=name, linewidth=1.6)
        for number, day in enumerate(markers):
            ax.axvline(
                # matplotlib.dates ships no type hints for date2num
                float(date2num(pd.Timestamp(day))),  # type: ignore[no-untyped-call]
                color="grey",
                linestyle=":",
                linewidth=1.0,
                label=marker_label if number == 0 and marker_label else None,
            )
        ax.set_title(title)
        ax.set_ylabel(y_label)
        if axis is AxisFormat.PERCENT:
            ax.yaxis.set_major_formatter(
                FuncFormatter(lambda v, _: format_percent(v, 1, style=style))
            )
        else:
            ax.yaxis.set_major_formatter(
                FuncFormatter(lambda v, _: format_number(v, 0, style=style))
            )
        if len(validated) > 1 or (markers and marker_label):
            ax.legend(loc="best", frameon=False)
        figure.tight_layout()
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=DPI, metadata={"Software": None})
    return buffer.getvalue()
