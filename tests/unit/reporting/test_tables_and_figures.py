"""Tables and deterministic PNG figures (Matplotlib Agg, no pyplot global state)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.reporting.figures import AxisFormat, line_figure
from qrlab.reporting.formatting import EN, IT
from qrlab.reporting.tables import Table

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _series() -> pd.Series:
    return pd.Series(
        [100.0, 103.0, 101.5, 108.0], index=pd.date_range("2026-01-30", periods=4, freq="ME")
    )


# --------------------------------------------------------------------------- tables
def test_table_validates_shape_and_alignment() -> None:
    table = Table(
        title="Positions",
        columns=("ISIN", "Value"),
        rows=(("IE0000000012", "2.700,00"),),
        align=("left", "right"),
        notes=("Values in EUR.",),
    )
    assert table.columns == ("ISIN", "Value")
    with pytest.raises(ValidationError, match="cells"):
        Table(title="T", columns=("a", "b"), rows=(("1",),), align=("left", "left"), notes=())
    with pytest.raises(ValidationError, match="align"):
        Table(title="T", columns=("a",), rows=(), align=("centre",), notes=())
    with pytest.raises(ValidationError, match="align"):
        Table(title="T", columns=("a", "b"), rows=(), align=("left",), notes=())
    with pytest.raises(ValidationError, match="column"):
        Table(title="T", columns=(), rows=(), align=(), notes=())


def test_table_cells_must_be_text() -> None:
    with pytest.raises(ValidationError, match="text"):
        Table(title="T", columns=("a",), rows=((1.5,),), align=("right",), notes=())  # type: ignore[arg-type]


# --------------------------------------------------------------------------- figures
def test_figure_is_a_png() -> None:
    png = line_figure(
        [("Value", _series())], title="Value", y_label="EUR", axis=AxisFormat.NUMBER, style=IT
    )
    assert png.startswith(PNG_SIGNATURE)
    assert len(png) > 1000


def test_figure_is_deterministic() -> None:
    kwargs = {"title": "TWR", "y_label": "%", "axis": AxisFormat.PERCENT, "style": EN}
    first = line_figure([("TWR", _series() / 100 - 1)], markers=[date(2026, 3, 31)], **kwargs)  # type: ignore[arg-type]
    second = line_figure([("TWR", _series() / 100 - 1)], markers=[date(2026, 3, 31)], **kwargs)  # type: ignore[arg-type]
    assert first == second


def test_figure_has_no_software_metadata() -> None:
    png = line_figure(
        [("Value", _series())], title="Value", y_label="EUR", axis=AxisFormat.NUMBER, style=IT
    )
    assert b"matplotlib" not in png.lower()
    assert b"tIME" not in png  # no PNG timestamp chunk


def test_figure_does_not_touch_pyplot_state() -> None:
    import matplotlib.pyplot as plt

    before = plt.get_fignums()
    line_figure(
        [("Value", _series())], title="Value", y_label="EUR", axis=AxisFormat.NUMBER, style=IT
    )
    assert plt.get_fignums() == before


def test_figure_validation() -> None:
    with pytest.raises(ValidationError, match="line"):
        line_figure([], title="x", y_label="y", axis=AxisFormat.NUMBER, style=IT)
    with pytest.raises(ValidationError, match="NaN"):
        line_figure(
            [
                (
                    "x",
                    pd.Series(
                        [1.0, float("nan")], index=pd.date_range("2026-01-31", periods=2, freq="ME")
                    ),
                )
            ],
            title="x",
            y_label="y",
            axis=AxisFormat.NUMBER,
            style=IT,
        )
    with pytest.raises(ValidationError, match="AxisFormat"):
        line_figure([("Value", _series())], title="x", y_label="y", axis="percent", style=IT)  # type: ignore[arg-type]


def test_figures_differ_when_data_differ() -> None:
    a = line_figure(
        [("Value", _series())], title="Value", y_label="EUR", axis=AxisFormat.NUMBER, style=IT
    )
    b = line_figure(
        [("Value", _series() * 2)], title="Value", y_label="EUR", axis=AxisFormat.NUMBER, style=IT
    )
    assert a != b


def test_figure_with_two_lines_and_marker_legend() -> None:
    png = line_figure(
        [("Portfolio", _series()), ("Benchmark", _series() * 0.99)],
        title="Value",
        y_label="EUR",
        axis=AxisFormat.NUMBER,
        style=EN,
        markers=[date(2026, 2, 28)],
        marker_label="Flows",
    )
    assert png.startswith(PNG_SIGNATURE)


def test_figure_note_is_drawn_without_changing_the_size() -> None:
    """Design note 7.2: an empty note changes nothing; a note is a footer of the same image."""
    kwargs = {"title": "Value", "y_label": "EUR", "axis": AxisFormat.NUMBER, "style": EN}
    plain = line_figure([("Value", _series())], **kwargs)  # type: ignore[arg-type]
    assert line_figure([("Value", _series())], note="", **kwargs) == plain  # type: ignore[arg-type]
    noted = line_figure([("Value", _series())], note="Scenarios, not a forecast.", **kwargs)  # type: ignore[arg-type]
    assert noted.startswith(PNG_SIGNATURE)
    assert noted != plain
    assert noted[16:24] == plain[16:24]  # PNG width and height
