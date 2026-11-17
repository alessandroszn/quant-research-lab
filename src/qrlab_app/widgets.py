"""Reusable Qt pieces: tables, the results panel, dialogs and the settings file."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSettings,
    Qt,
    QUrl,
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

from qrlab_app.chart_widgets import ChartView
from qrlab_app.charts import ChartModel
from qrlab_app.display import cell_text, date_text
from qrlab_app.pdf import export_pdf
from qrlab_app.strings import tr, tr_value
from qrlab_app.viewmodels import ResultView

__all__ = [
    "Dialogs",
    "FrameModel",
    "QtSettingsStore",
    "ResultsPanel",
    "default_dialogs",
    "fill_table",
]

_ModelIndex = QModelIndex | QPersistentModelIndex


class FrameModel(QAbstractTableModel):
    """Read-only view of a DataFrame (index as the first column), formatted for a language."""

    def __init__(self, frame: pd.DataFrame, language: str) -> None:
        """Show ``frame`` with its index as the first column."""
        super().__init__()
        self._frame = frame.reset_index()
        self._language = language

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
        return cell_text(self._frame.iloc[index.row(), index.column()], self._language)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """Column names (as recorded) and row numbers."""
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._frame.columns[section])
        return str(section + 1)


def fill_table(
    table: QTableWidget,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    language: str,
) -> None:
    """Replace a table widget's content with cells formatted for ``language``."""
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(cell_text(value, language)))
    table.resizeColumnsToContents()


class ResultsPanel(QWidget):
    """Tables (with their sample tag), scalars, figures and links to the report and folder.

    A dated table also gets a Chart view next to its Table view (design note 12.3b); the charts
    of the result shown are in :attr:`charts`.
    """

    def __init__(
        self,
        language: str,
        open_path: Callable[[Path], None],
        pick_save_file: Callable[[str, str], Path | None] | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        """Build an empty panel; without ``pick_save_file`` a report cannot be exported."""
        super().__init__()
        self._language = language
        self._open_path = open_path
        self._pick_save_file = pick_save_file
        self._today = today
        self._view: ResultView | None = None
        self.charts: list[ChartView] = []
        self.title = QLabel("")
        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        self.tabs = QTabWidget()
        self.report_button = QPushButton(tr("screen.open_report", language))
        self.folder_button = QPushButton(tr("screen.open_folder", language))
        self.pdf_button = QPushButton(tr("results.export_pdf", language))
        self.report_button.clicked.connect(self._open_report)
        self.folder_button.clicked.connect(self._open_folder)
        self.pdf_button.clicked.connect(self._export_pdf)
        self.export_message = QLabel("")
        self.export_message.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.report_button)
        buttons.addWidget(self.pdf_button)
        buttons.addWidget(self.folder_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.notice)
        layout.addWidget(self.tabs)
        layout.addLayout(buttons)
        layout.addWidget(self.export_message)
        self.show_result(None)

    def show_result(self, view: ResultView | None) -> None:
        """Display a result, or clear the panel."""
        self._view = view
        self.tabs.clear()
        self.charts = []
        has_report = view is not None and view.report is not None
        self.report_button.setEnabled(has_report)
        self.pdf_button.setEnabled(has_report and self._pick_save_file is not None)
        self.export_message.setText("")
        self.folder_button.setEnabled(view is not None)
        self.notice.setText("" if view is None or not view.notice else view.notice)
        if view is None:
            self.title.setText("")
            return
        language = self._language
        self.title.setText(f"{view.output_dir.name}: {tr_value('status', view.status, language)}")
        for table in view.tables:
            grid = QTableView()
            grid.setModel(FrameModel(table.frame, language))
            chart = ChartModel.from_frame(table.frame)
            widget: QWidget = grid
            if chart is not None:
                views = QTabWidget()
                views.addTab(grid, tr("results.table", language))
                chart_view = ChartView(chart, language)
                views.addTab(chart_view, tr("results.chart", language))
                self.charts.append(chart_view)
                widget = views
            self.tabs.addTab(widget, f"{table.name} [{tr_value('tag', table.tag, language)}]")
        if view.scalars:
            scalars = QTableWidget()
            rows = [
                (name, value, tr_value("tag", tag, language)) for name, value, tag in view.scalars
            ]
            fill_table(scalars, tr("results.scalar_columns", language).split("|"), rows, language)
            self.tabs.addTab(scalars, tr("results.scalars", language))
        if view.figures:
            box = QWidget()
            column = QVBoxLayout(box)
            for figure in view.figures:
                label = QLabel()
                label.setPixmap(QPixmap(str(figure)))
                column.addWidget(label)
            scroll = QScrollArea()
            scroll.setWidget(box)
            self.tabs.addTab(scroll, tr("results.figures", language))

    def output_name(self) -> str:
        """Return the name of the shown result's output folder (empty when none is shown)."""
        return "" if self._view is None else self._view.output_dir.name

    def _open_report(self) -> None:
        if self._view is not None and self._view.report is not None:
            self._open_path(self._view.report)

    def _open_folder(self) -> None:
        if self._view is not None:
            self._open_path(self._view.output_dir)

    def _export_pdf(self) -> None:
        """Ask where to save, then print the report to a PDF there (design note 12.4)."""
        view, language = self._view, self._language
        if view is None or view.report is None or self._pick_save_file is None:
            return
        if not view.report.is_file():
            self.export_message.setText(tr("pdf.missing", language, path=view.report))
            return
        folder = view.output_dir.name
        target = self._pick_save_file(tr("results.export_pdf", language), f"{folder}.pdf")
        if target is None:
            return
        header = tr("pdf.header", language, folder=folder, day=date_text(self._today(), language))
        try:
            export_pdf(view.report, target, header=header, title=folder)
        except OSError as exc:
            self.export_message.setText(tr("pdf.failed", language, error=exc))
            return
        self.export_message.setText(tr("pdf.saved", language, path=target))


class QtSettingsStore:
    """Settings in an INI file through ``QSettings`` (never the Windows registry)."""

    def __init__(self, settings: QSettings) -> None:
        """Wrap ``settings``, which must use the INI format."""
        if settings.format() != QSettings.Format.IniFormat:
            raise ValueError("settings must use the INI format")
        self._settings = settings

    @classmethod
    def at(cls, path: Path) -> QtSettingsStore:
        """Use the INI file at ``path`` (tests)."""
        return cls(QSettings(str(path), QSettings.Format.IniFormat))

    @classmethod
    def for_user(cls) -> QtSettingsStore:  # pragma: no cover - writes to the user's profile
        """Use the user's file (on Windows ``%APPDATA%/qrlab/qrlab-app.ini``)."""
        return cls(
            QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "qrlab", "qrlab-app")
        )

    @property
    def file_name(self) -> str:
        """Where the settings are written."""
        return self._settings.fileName()

    def get(self, key: str) -> str | None:
        """Return the stored value or ``None``."""
        value = self._settings.value(key)
        return None if value is None else str(value)

    def set(self, key: str, value: str) -> None:
        """Store a value and write the file."""
        self._settings.setValue(key, value)
        self._settings.sync()


@dataclass(frozen=True)
class Dialogs:
    """Everything that needs a user's answer (replaced by fakes in tests).

    ``ask_save`` answers ``"save"``, ``"discard"`` or ``None`` (cancel).
    """

    pick_folder: Callable[[str], Path | None]
    ask_text: Callable[[str], str | None]
    ask_choice: Callable[[str, Sequence[str]], str | None]
    confirm: Callable[[str], bool]
    ask_save: Callable[[str], str | None]
    inform: Callable[[str], None]
    open_path: Callable[[Path], None]
    pick_file: Callable[[str], Path | None]
    pick_save_file: Callable[[str, str], Path | None]  # title, suggested file name


def default_dialogs(parent: QWidget | None) -> Dialogs:  # pragma: no cover - needs a user
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

    def ask_save(question: str) -> str | None:
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            parent, "", question, buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save
        )
        return {buttons.Save: "save", buttons.Discard: "discard"}.get(answer)

    def inform(message: str) -> None:
        QMessageBox.information(parent, "", message)

    def open_path(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def pick_file(title: str) -> Path | None:
        file, _ = QFileDialog.getOpenFileName(parent, title)
        return Path(file) if file else None

    def pick_save_file(title: str, name: str) -> Path | None:
        file, _ = QFileDialog.getSaveFileName(parent, title, name, "PDF (*.pdf)")
        return Path(file) if file else None

    return Dialogs(
        pick_folder,
        ask_text,
        ask_choice,
        confirm,
        ask_save,
        inform,
        open_path,
        pick_file,
        pick_save_file,
    )
