"""Reusable Qt pieces: tables, the results panel, the run worker, dialogs and the settings file."""

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
    QSettings,
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

from qrlab_app.display import cell_text
from qrlab_app.strings import tr, tr_value
from qrlab_app.viewmodels import ResultView

__all__ = [
    "Dialogs",
    "FrameModel",
    "QtSettingsStore",
    "ResultsPanel",
    "RunWorker",
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
    """Tables (with their sample tag), scalars, figures and links to the report and folder."""

    def __init__(self, language: str, open_path: Callable[[Path], None]) -> None:
        """Build an empty panel."""
        super().__init__()
        self._language = language
        self._open_path = open_path
        self._view: ResultView | None = None
        self.title = QLabel("")
        self.notice = QLabel("")
        self.notice.setWordWrap(True)
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
        layout.addWidget(self.notice)
        layout.addWidget(self.tabs)
        layout.addLayout(buttons)
        self.show_result(None)

    def show_result(self, view: ResultView | None) -> None:
        """Display a result, or clear the panel."""
        self._view = view
        self.tabs.clear()
        self.report_button.setEnabled(view is not None and view.report is not None)
        self.folder_button.setEnabled(view is not None)
        self.notice.setText("" if view is None or not view.notice else view.notice)
        if view is None:
            self.title.setText("")
            return
        language = self._language
        self.title.setText(f"{view.output_dir.name}: {tr_value('status', view.status, language)}")
        for table in view.tables:
            widget = QTableView()
            widget.setModel(FrameModel(table.frame, language))
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

    return Dialogs(pick_folder, ask_text, ask_choice, confirm, ask_save, inform, open_path)
