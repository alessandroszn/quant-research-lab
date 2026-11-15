"""The Portfolio screen (phase 8.8b): describe a portfolio in two tables, then build a report.

The widgets only show :class:`qrlab_app.portfolio.PortfolioViewModel` and forward edits to it;
every check and every file is the library's.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qrlab.experiments.portfolios import INSTRUMENT_FIELDS, NATIVE_COLUMNS, TRANSACTION_KINDS
from qrlab_app.portfolio import PortfolioViewModel, Problem
from qrlab_app.strings import tr
from qrlab_app.viewmodels import AppError
from qrlab_app.widgets import Dialogs

__all__ = ["KIND_COLUMN", "PortfolioScreen"]

KINDS = TRANSACTION_KINDS
KIND_COLUMN = NATIVE_COLUMNS.index("kind")


class PortfolioScreen(QWidget):
    """Portfolios of the workspace; transactions and instruments of the selected one."""

    def __init__(
        self,
        model: PortfolioViewModel,
        dialogs: Dialogs,
        language: str,
        *,
        on_report: Callable[[Path], None],
    ) -> None:
        """Build the screen; ``on_report`` opens a report config it created."""
        super().__init__()
        self.model = model
        self.dialogs = dialogs
        self.language = language
        self.on_report = on_report
        self._loading = False
        self.portfolios = QListWidget()
        self.portfolios.itemClicked.connect(self._selected)
        self.new_button = QPushButton(tr("portfolio.new", language))
        self.new_button.clicked.connect(self._new)
        self.refresh_button = QPushButton(tr("screen.refresh", language))
        self.refresh_button.clicked.connect(self.refresh)
        self.transactions = QTableWidget()
        self.transactions.itemChanged.connect(self._transaction_edited)
        self.instruments = QTableWidget()
        self.instruments.itemChanged.connect(self._instrument_edited)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.transactions, tr("portfolio.transactions", language))
        self.tabs.addTab(self.instruments, tr("portfolio.instruments", language))
        self.add_button = QPushButton(tr("portfolio.add_row", language))
        self.add_instrument_button = QPushButton(tr("portfolio.add_instrument", language))
        self.remove_button = QPushButton(tr("portfolio.remove", language))
        self.start_button = QPushButton(tr("portfolio.start", language))
        self.save_button = QPushButton(tr("portfolio.save", language))
        self.report_button = QPushButton(tr("portfolio.create_report", language))
        self.add_button.clicked.connect(self._add_transaction)
        self.add_instrument_button.clicked.connect(self._add_instrument)
        self.remove_button.clicked.connect(self._remove)
        self.start_button.clicked.connect(self._start)
        self.save_button.clicked.connect(self._save)
        self.report_button.clicked.connect(self._report)
        self.message = QLabel("")
        self.message.setWordWrap(True)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel(tr("portfolio.list", language)))
        left_layout.addWidget(self.portfolios)
        left_layout.addWidget(self.new_button)
        left_layout.addWidget(self.refresh_button)
        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.addWidget(self.tabs)
        edit_row = QHBoxLayout()
        for button in (
            self.add_button,
            self.add_instrument_button,
            self.remove_button,
            self.start_button,
        ):
            edit_row.addWidget(button)
        file_row = QHBoxLayout()
        file_row.addWidget(self.save_button)
        file_row.addWidget(self.report_button)
        centre_layout.addLayout(edit_row)
        centre_layout.addLayout(file_row)
        centre_layout.addWidget(self.message)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(centre)
        splitter.setSizes([220, 1060])
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self._render()

    # ------------------------------------------------------------------------ actions
    def refresh(self) -> None:
        """Reload the list of portfolios."""
        try:
            names = self.model.refresh()
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        self.portfolios.clear()
        for name in names:
            item = QListWidgetItem(name)
            self.portfolios.addItem(item)
            if name == self.model.selected:
                self.portfolios.setCurrentItem(item)
        self._enable()

    def reset(self) -> None:
        """Forget the selection and reload (another workspace was opened)."""
        self.model.clear()
        self.message.setText("")
        self._render()
        self.refresh()

    def confirm_discard(self) -> bool:
        """Ask what to do with unsaved edits; ``False`` means stay (cancelled or not valid)."""
        if not self.model.dirty or self.model.selected is None:
            return True
        answer = self.dialogs.ask_save(
            tr("portfolio.unsaved", self.language, name=self.model.selected)
        )
        if answer == "save":
            return self._save()
        if answer == "discard":
            self.model.revert()
            self._render()
            return True
        return False

    def _selected(self, item: QListWidgetItem) -> None:
        name = item.text()
        if name == self.model.selected:
            return
        if not self.confirm_discard():
            self.refresh()
            return
        self._guard(lambda: self.model.select(name))

    def _new(self) -> None:
        if not self.confirm_discard():
            return
        name = self.dialogs.ask_text(tr("portfolio.new_name", self.language))
        if name is not None:
            self._guard(lambda: self.model.create(name))

    def _add_transaction(self) -> None:
        kind = self.dialogs.ask_choice(tr("portfolio.kind", self.language), KINDS)
        if kind is not None:
            self._guard(lambda: self.model.add_transaction(kind))
            self.tabs.setCurrentWidget(self.transactions)

    def _add_instrument(self) -> None:
        self._guard(self.model.add_instrument)
        self.tabs.setCurrentWidget(self.instruments)

    def _remove(self) -> None:
        on_transactions = self.tabs.currentWidget() is self.transactions
        table = self.transactions if on_transactions else self.instruments
        row = table.currentRow()
        if row < 0:
            return
        if on_transactions:
            self.model.remove_transaction(row)
        else:
            self.model.remove_instrument(row)
        self._render()

    def _start(self) -> None:
        day = self.dialogs.ask_text(tr("portfolio.start_date", self.language))
        if day is None:
            return
        if self._guard(lambda: self.model.add_starting_position(day)):
            self.tabs.setCurrentWidget(self.transactions)
            self.message.setText(tr("portfolio.start_added", self.language, day=day.strip()))

    def _save(self) -> bool:
        try:
            problem = self.model.save()
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return False
        if problem is not None:
            self._show_problem(problem)
            return False
        self._render()
        self.message.setText(
            tr(
                "portfolio.saved",
                self.language,
                transactions=len(self.model.transactions),
                instruments=len(self.model.instruments),
            )
        )
        return True

    def _report(self) -> None:
        name = self.dialogs.ask_text(tr("portfolio.report_name", self.language))
        if name is None:
            return
        try:
            path = self.model.create_report(name)
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        self.message.setText(tr("portfolio.report_created", self.language, name=path.name))
        self.on_report(path)

    # ------------------------------------------------------------------------ display
    def _guard(self, action: Callable[[], object]) -> bool:
        try:
            action()
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return False
        self.message.setText("")
        self._render()
        self.refresh()
        return True

    def _show_problem(self, problem: Problem) -> None:
        table = self.transactions if problem.table == "transactions" else self.instruments
        self.tabs.setCurrentWidget(table)
        name = tr(f"portfolio.{problem.table}", self.language)
        error = tr(problem.key, self.language, **problem.values)
        if problem.row is None:
            text = tr("portfolio.problem_no_row", self.language, table=name, error=error)
        else:
            table.selectRow(problem.row)
            text = tr(
                "portfolio.problem", self.language, table=name, row=problem.row + 1, error=error
            )
        self.message.setText(text)

    def _render(self) -> None:
        self._loading = True
        rows = self.model.transactions
        self.transactions.clear()
        self.transactions.setColumnCount(len(NATIVE_COLUMNS))
        self.transactions.setHorizontalHeaderLabels(list(NATIVE_COLUMNS))
        self.transactions.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, column in enumerate(NATIVE_COLUMNS):
                if c == KIND_COLUMN:
                    self.transactions.setCellWidget(r, c, self._kind_box(r, row["kind"]))
                    continue
                item = QTableWidgetItem(row[column])
                if not self.model.editable(r, column):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(self.palette().window())
                self.transactions.setItem(r, c, item)
        instruments = self.model.instruments
        self.instruments.clear()
        self.instruments.setColumnCount(len(INSTRUMENT_FIELDS))
        self.instruments.setHorizontalHeaderLabels(list(INSTRUMENT_FIELDS))
        self.instruments.setRowCount(len(instruments))
        for r, fields in enumerate(instruments):
            for c, name in enumerate(INSTRUMENT_FIELDS):
                self.instruments.setItem(r, c, QTableWidgetItem(fields[name]))
        self.transactions.resizeColumnsToContents()
        self.instruments.resizeColumnsToContents()
        self._loading = False
        self._enable()

    def _kind_box(self, row: int, kind: str) -> QComboBox:
        box = QComboBox()
        box.addItems(KINDS)
        box.setCurrentText(kind)
        box.currentTextChanged.connect(lambda text: self._kind_changed(row, text))
        return box

    def _kind_changed(self, row: int, kind: str) -> None:
        # Connected after the box is filled, so it never fires while the table is rendered.
        self.model.set_transaction(row, "kind", kind)
        self._render()

    def _transaction_edited(self, item: QTableWidgetItem) -> None:
        if not self._loading:
            self.model.set_transaction(item.row(), NATIVE_COLUMNS[item.column()], item.text())

    def _instrument_edited(self, item: QTableWidgetItem) -> None:
        if not self._loading:
            self.model.set_instrument(item.row(), INSTRUMENT_FIELDS[item.column()], item.text())

    def _enable(self) -> None:
        open_workspace = self.model.workspace.root is not None
        selected = self.model.selected is not None
        self.new_button.setEnabled(open_workspace)
        for button in (
            self.add_button,
            self.add_instrument_button,
            self.remove_button,
            self.start_button,
            self.save_button,
            self.report_button,
        ):
            button.setEnabled(selected)
