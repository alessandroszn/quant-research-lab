"""Reusable Qt pieces: a read-only DataFrame model, the results panel, the run worker, dialogs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRunnable,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qrlab_app.strings import tr
from qrlab_app.viewmodels import ResultView

__all__ = ["Dialogs", "FrameModel", "ResultsPanel", "RunWorker", "default_dialogs", "fill_table"]

_ModelIndex = QModelIndex | QPersistentModelIndex


class FrameModel(QAbstractTableModel):
    """Read-only view of a DataFrame (index as the first column)."""

    def __init__(self, frame: pd.DataFrame) -> None:
        """Show ``frame`` with its index as the first column."""
        super().__init__()
        self._frame = frame.reset_index()

    def rowCount(self, parent: _ModelIndex = QModelIndex()) -> int:  # noqa: N802, B008
        """Return the number of rows."""
        return 0 if parent.isValid() else len(self._frame)

    def columnCount(self, parent: _ModelIndex = QModelIndex()) -> int:  # noqa: N802, B008
        """Return the number of columns."""
        return 0 if parent.isValid() else len(self._frame.columns)

    def data(self, index: _ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Cell text (``display`` role only)."""
        if role != Qt.ItemDataRole.DisplayRole or not index.isValid():
            return None
        return _text(self._frame.iloc[index.row(), index.column()])

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """Column names and row numbers."""
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._frame.columns[section])
        return str(section + 1)


def _text(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return "" if value is None else str(value)


def fill_table(
    table: QTableWidget, headers: Sequence[str], rows: Sequence[Sequence[object]]
) -> None:
    """Replace a table widget's content with text cells."""
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(_text(value)))
    table.resizeColumnsToContents()


class ResultsPanel(QWidget):
    """Tables (with their sample tag), scalars, figures and links to the report and folder."""

    def __init__(self, language: str, open_path: Callable[[Path], None]) -> None:
        """Build an empty panel."""
        super().__init__()
        self._language = language
        self._open_path = open_path
        self._view: ResultView | None = None
        self.title = QLabel("")
        self.tabs = QTabWidget()
        self.report_button = QPushButton(tr("screen.open_report", language))
        self.folder_button = QPushButton(tr("screen.open_folder", language))
        self.report_button.clicked.connect(self._open_report)
        self.folder_button.clicked.connect(self._open_folder)
        buttons = QHBoxLayout()
        buttons.addWidget(self.report_button)
        buttons.addWidget(self.folder_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.tabs)
        layout.addLayout(buttons)
        self.show_result(None)

    def show_result(self, view: ResultView | None) -> None:
        """Display a result, or clear the panel."""
        self._view = view
        self.tabs.clear()
        self.report_button.setEnabled(view is not None and view.report is not None)
        self.folder_button.setEnabled(view is not None)
        if view is None:
            self.title.setText("")
            return
        self.title.setText(f"{view.output_dir.name}: {view.status}")
        for table in view.tables:
            widget = QTableView()
            widget.setModel(FrameModel(table.frame))
            self.tabs.addTab(widget, f"{table.name} [{table.tag}]")
        if view.scalars:
            scalars = QTableWidget()
            fill_table(scalars, ("name", "value", "tag"), view.scalars)
            self.tabs.addTab(scalars, tr("results.scalars", self._language))
        if view.figures:
            box = QWidget()
            column = QVBoxLayout(box)
            for figure in view.figures:
                label = QLabel()
                label.setPixmap(QPixmap(str(figure)))
                column.addWidget(label)
            scroll = QScrollArea()
            scroll.setWidget(box)
            self.tabs.addTab(scroll, tr("results.figures", self._language))

    def _open_report(self) -> None:
        if self._view is not None and self._view.report is not None:
            self._open_path(self._view.report)

    def _open_folder(self) -> None:
        if self._view is not None:
            self._open_path(self._view.output_dir)


class _WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class RunWorker(QRunnable):
    """Run a job off the GUI thread; report the result or the exception through signals."""

    def __init__(self, job: Callable[[], object]) -> None:
        """Wrap ``job``."""
        super().__init__()
        self.job = job
        self.signals = _WorkerSignals()

    def run(self) -> None:
        """Run the job (called by the thread pool)."""
        try:
            result = self.job()
        except Exception as exc:  # reported to the user, never lost in a thread
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.finished.emit(result)


@dataclass(frozen=True)
class Dialogs:
    """Everything that needs a user's answer (replaced by fakes in tests)."""

    pick_folder: Callable[[str], Path | None]
    ask_text: Callable[[str], str | None]
    ask_choice: Callable[[str, Sequence[str]], str | None]
    confirm: Callable[[str], bool]
    open_path: Callable[[Path], None]


def default_dialogs(parent: QWidget) -> Dialogs:  # pragma: no cover - needs a user
    """Real Qt dialogs."""

    def pick_folder(title: str) -> Path | None:
        folder = QFileDialog.getExistingDirectory(parent, title)
        return Path(folder) if folder else None

    def ask_text(prompt: str) -> str | None:
        text, ok = QInputDialog.getText(parent, "", prompt)
        return text if ok else None

    def ask_choice(prompt: str, options: Sequence[str]) -> str | None:
        item, ok = QInputDialog.getItem(parent, "", prompt, list(options), 0, False)
        return item if ok else None

    def confirm(question: str) -> bool:
        answer = QMessageBox.question(parent, "", question)
        return bool(answer == QMessageBox.StandardButton.Yes)

    def open_path(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    return Dialogs(pick_folder, ask_text, ask_choice, confirm, open_path)
