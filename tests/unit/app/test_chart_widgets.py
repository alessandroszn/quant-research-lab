"""Interactive charts off-screen (design note 12.3b): which outputs get one, and the widget."""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from matplotlib import dates as mdates
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTabWidget

from qrlab.experiments import run_experiment
from qrlab.experiments.kinds import KINDS
from qrlab_app.chart_widgets import ChartView
from qrlab_app.charts import MAX_LINES, ChartModel
from qrlab_app.viewmodels import ResultView, TableView, load_result
from qrlab_app.widgets import ResultsPanel

ROOT = Path(__file__).parents[3]
CONFIGS = ROOT / "configs" / "experiments"
CHARTABLE = {
    "example_backtest.toml": ["values", "weights"],
    "example_optimisation.toml": [],
    "example_portfolio_report.toml": ["twr", "value"],
    "example_portfolio_report_full.toml": ["twr", "value"],
    "example_projection.toml": ["fan_real"],
    "example_risk_report.toml": ["var_backtest"],
    "example_scenarios.toml": [],
}


def _localise(name: str, tmp: Path) -> Path:
    text = (CONFIGS / name).read_text(encoding="utf-8").replace("paths = 5000", "paths = 50")
    text = text.replace('"../../', f'"{ROOT.as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    directory = tomllib.loads(text)["output"]["directory"]
    text = text.replace(f'directory = "{directory}"', f'directory = "{(tmp / "out").as_posix()}"')
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


def test_every_example_lists_its_charts() -> None:
    assert sorted(CHARTABLE) == sorted(p.name for p in CONFIGS.glob("example_*.toml"))


@pytest.mark.parametrize(("name", "expected"), sorted(CHARTABLE.items()))
def test_which_outputs_are_charts(tmp_path: Path, name: str, expected: list[str]) -> None:
    result = run_experiment(_localise(name, tmp_path), kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    view = load_result(result.output_dir)
    charts = sorted(t.name for t in view.tables if ChartModel.from_frame(t.frame) is not None)
    assert charts == expected


def _chart(columns: int = 2) -> ChartModel:
    index = ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]
    data = {
        f"line_{n:02d}": [100.0 + n, 101.0 + n, float("nan"), 103.0 + n] for n in range(columns)
    }
    chart = ChartModel.from_frame(pd.DataFrame(data, index=index))
    assert chart is not None
    return chart


def test_the_chart_is_drawn_once_and_only_when_shown(qapp: QApplication) -> None:
    view = ChartView(_chart(), "en")
    assert (view.drawn, view.lines) == (False, {})
    view.show()
    assert view.drawn  # the first show draws it
    lines = dict(view.lines)
    view.draw()
    assert view.lines == lines  # once
    assert len(view.axes.get_lines()) == 2 + 1  # two series and the cursor line
    assert isinstance(view.toolbar, NavigationToolbar2QT)
    assert view.choices.isVisibleTo(view)
    view.close()


def test_the_cursor_and_the_readout(qapp: QApplication) -> None:
    view = ChartView(_chart(), "it")
    view.resize(800, 500)
    view.draw()
    view.canvas.draw()  # type: ignore[no-untyped-call]  # the transforms need a drawn canvas
    day = date(2026, 2, 28)
    where = mdates.date2num(day)  # type: ignore[no-untyped-call]
    x, y = view.axes.transData.transform((where, 101.0))
    event = MouseEvent("motion_notify_event", view.canvas, x, y)
    view.canvas.callbacks.process("motion_notify_event", event)
    assert view.readout.text() == "28/02/2026  ·  line_00: 101  ·  line_01: 102"
    assert view.marker is not None
    assert view.marker.get_visible()
    outside = MouseEvent("motion_notify_event", view.canvas, -50, -50)
    view.canvas.callbacks.process("motion_notify_event", outside)
    assert view.readout.text().startswith("28/02/2026")  # unchanged off the axes
    view.point_at(date(2026, 3, 30))
    assert view.readout.text() == "31/03/2026  ·  line_00: —  ·  line_01: —"  # a gap


def test_tick_boxes_show_and_hide_lines(qapp: QApplication) -> None:
    view = ChartView(_chart(10), "en")
    assert view.choices.count() == 10
    checked = [view.choices.item(i).checkState() == Qt.CheckState.Checked for i in range(10)]
    assert checked == [True] * MAX_LINES + [False] * 2
    view.choices.item(9).setCheckState(Qt.CheckState.Checked)  # before drawing: drawn first
    assert view.drawn
    assert view.shown() == [f"line_{n:02d}" for n in [*range(MAX_LINES), 9]]
    for row in range(10):
        view.choices.item(row).setCheckState(Qt.CheckState.Unchecked)
    assert view.shown() == []
    assert view.axes.get_legend() is None  # no lines, no legend
    view.choices.item(0).setCheckState(Qt.CheckState.Checked)
    legend = view.axes.get_legend()
    assert legend is not None
    assert [t.get_text() for t in legend.get_texts()] == ["line_00"]
    view.point_at(date(2026, 1, 1))
    assert view.readout.text() == "2026-01-31  ·  line_00: 100"


def test_one_line_needs_no_tick_boxes(qapp: QApplication) -> None:
    view = ChartView(_chart(1), "en")
    assert not view.choices.isVisibleTo(view)
    assert not view.choices_label.isVisibleTo(view)


def test_the_results_panel_puts_a_chart_next_to_dated_tables(
    qapp: QApplication, tmp_path: Path
) -> None:
    dated = pd.DataFrame({"x": [1.0, 2.0]}, index=["2026-01-31", "2026-02-28"])
    named = pd.DataFrame({"weight": [0.6, 0.4]}, index=["equity", "bonds"])
    view = ResultView(
        output_dir=tmp_path,
        status="success",
        error=None,
        tables=(
            TableView("series", "descriptive", dated),
            TableView("weights", "in_sample", named),
        ),
        scalars=(),
        figures=(),
        report=None,
    )
    panel = ResultsPanel("it", lambda path: None)
    panel.show_result(view)
    assert len(panel.charts) == 1
    series_tab = panel.tabs.widget(0)
    assert isinstance(series_tab, QTabWidget)
    assert [series_tab.tabText(i) for i in range(2)] == ["Tabella", "Grafico"]
    assert not isinstance(panel.tabs.widget(1), QTabWidget)  # no chart for named rows
    panel.show_result(None)
    assert panel.charts == []
