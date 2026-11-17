"""Interactive charts of dated tables, on Matplotlib's Qt canvas (design note 12.3b).

The chart draws each numeric column of a dated table as it is written: nothing is computed.
Matplotlib's own toolbar zooms, pans, goes back and forward and saves an image; a vertical line
follows the cursor and the readout below gives the nearest date's values in the app's
language. Tick boxes show or hide the lines (at most eight are shown at first).

The chart is drawn the first time it is shown, so a result with many tables opens quickly.
"""

from __future__ import annotations

from datetime import date

from matplotlib import dates as mdates
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from qrlab_app.charts import ChartModel
from qrlab_app.display import cell_text
from qrlab_app.strings import tr

__all__ = ["ChartView"]

_LIST_HEIGHT = 90  # pixels: the tick boxes stay a short strip under the chart


class ChartView(QWidget):
    """One dated table as an interactive line chart."""

    def __init__(self, chart: ChartModel, language: str) -> None:
        """Prepare the chart of ``chart``; it is drawn when first shown (or by :meth:`draw`)."""
        super().__init__()
        self.chart = chart
        self.language = language
        self.drawn = False
        self.lines: dict[str, Line2D] = {}
        self.marker: Line2D | None = None
        self.figure = Figure(figsize=(8, 4), layout="constrained")
        self.axes = self.figure.add_subplot()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.readout = QLabel("")
        self.readout.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.choices = QListWidget()
        self.choices.setMaximumHeight(_LIST_HEIGHT)
        shown = set(chart.shown_at_first)
        for name in chart.columns:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in shown else Qt.CheckState.Unchecked)
            self.choices.addItem(item)
        self.choices.itemChanged.connect(self._toggled)
        self.choices.setVisible(len(chart.columns) > 1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.readout)
        self.choices_label = QLabel(tr("results.lines", language))
        self.choices_label.setVisible(len(chart.columns) > 1)
        layout.addWidget(self.choices_label)
        layout.addWidget(self.choices)

    # ------------------------------------------------------------------------ drawing
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Draw the chart the first time it is shown."""
        super().showEvent(event)
        self.draw()

    def draw(self) -> None:
        """Draw the lines once; later calls do nothing."""
        if self.drawn:
            return
        chart, axes = self.chart, self.axes
        days = mdates.date2num(chart.dates)  # Matplotlib's day numbers, for the date axis
        for row, name in enumerate(chart.columns):
            (line,) = axes.plot(days, chart.series[name], label=name, linewidth=1.2)
            item = self.choices.item(row)
            line.set_visible(item.checkState() == Qt.CheckState.Checked)
            self.lines[name] = line
        locator = mdates.AutoDateLocator()
        axes.xaxis.set_major_locator(locator)
        axes.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        axes.yaxis.set_major_formatter(
            FuncFormatter(lambda value, _: cell_text(float(value), self.language))
        )
        axes.grid(alpha=0.3)
        first = float(mdates.date2num(chart.dates[0]))
        self.marker = axes.axvline(first, color="0.4", linewidth=0.8, visible=False)
        self._legend()
        self.canvas.mpl_connect("motion_notify_event", self._moved)
        self.canvas.draw_idle()
        self.drawn = True

    def point_at(self, when: date) -> None:
        """Move the cursor line to the date nearest ``when`` and show its values."""
        self.draw()
        assert self.marker is not None  # set by draw
        position = self.chart.nearest(when)
        day = self.chart.dates[position]
        where = float(mdates.date2num(day))
        self.marker.set_xdata([where, where])
        self.marker.set_visible(True)
        self.readout.setText(self.chart.readout(position, self.shown(), self.language))
        self.canvas.draw_idle()

    def shown(self) -> list[str]:
        """Return the columns whose lines are shown, in the table's order."""
        return [name for name in self.chart.columns if self.lines[name].get_visible()]

    # ------------------------------------------------------------------------ events
    def _moved(self, event: MouseEvent) -> None:
        if event.inaxes is not self.axes or event.xdata is None:
            return
        self.point_at(mdates.num2date(event.xdata).date())

    def _toggled(self, item: QListWidgetItem) -> None:
        self.draw()
        self.lines[item.text()].set_visible(item.checkState() == Qt.CheckState.Checked)
        self._legend()
        self.canvas.draw_idle()

    def _legend(self) -> None:
        visible = [self.lines[name] for name in self.shown()]
        legend = self.axes.get_legend()
        if legend is not None:
            legend.remove()
        if visible:
            self.axes.legend(handles=visible, loc="best", fontsize=8)
