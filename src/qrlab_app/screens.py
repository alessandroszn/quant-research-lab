"""The app's screens: Home, the analysis screens, Data and History."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from qrlab.experiments import RunResult
from qrlab_app.strings import tr
from qrlab_app.viewmodels import (
    AppError,
    DataViewModel,
    ExperimentViewModel,
    HistoryViewModel,
    WorkspaceViewModel,
)
from qrlab_app.widgets import Dialogs, ResultsPanel, RunWorker, fill_table

__all__ = ["DataScreen", "ExperimentScreen", "HistoryScreen", "HomeScreen"]


class HomeScreen(QWidget):
    """Open or create a workspace."""

    def __init__(
        self,
        workspace: WorkspaceViewModel,
        dialogs: Dialogs,
        language: str,
        on_change: Callable[[], None],
    ) -> None:
        """Build the screen; ``on_change`` runs after a workspace is opened."""
        super().__init__()
        self.workspace = workspace
        self.dialogs = dialogs
        self.language = language
        self.on_change = on_change
        self.path_label = QLabel(tr("home.none", language))
        self.message = QLabel("")
        self.open_button = QPushButton(tr("home.open", language))
        self.create_button = QPushButton(tr("home.create", language))
        self.open_button.clicked.connect(lambda: self._choose(create=False))
        self.create_button.clicked.connect(lambda: self._choose(create=True))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("app.disclaimer", language)))
        layout.addWidget(self.path_label)
        layout.addWidget(self.open_button)
        layout.addWidget(self.create_button)
        layout.addWidget(self.message)
        layout.addStretch()

    def _choose(self, *, create: bool) -> None:
        key = "home.create" if create else "home.open"
        folder = self.dialogs.pick_folder(tr(key, self.language))
        if folder is None:
            return
        try:
            root = self.workspace.create(folder) if create else self.workspace.open(folder)
        except AppError as exc:
            self.message.setText(str(exc))
            return
        self.message.setText("")
        self.path_label.setText(tr("home.current", self.language, path=root))
        self.on_change()


class ExperimentScreen(QWidget):
    """Configs of some kinds, a TOML editor with Validate and Run, and the results panel."""

    def __init__(
        self,
        model: ExperimentViewModel,
        dialogs: Dialogs,
        language: str,
        pool: QThreadPool,
    ) -> None:
        """Build the screen around its view-model."""
        super().__init__()
        self.model = model
        self.dialogs = dialogs
        self.language = language
        self.pool = pool
        self._started = 0.0
        self.configs = QListWidget()
        self.configs.itemClicked.connect(self._selected)
        self.new_button = QPushButton(tr("screen.new", language))
        self.duplicate_button = QPushButton(tr("screen.duplicate", language))
        self.refresh_button = QPushButton(tr("screen.refresh", language))
        self.new_button.clicked.connect(self._new)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.refresh_button.clicked.connect(self.refresh)
        self.editor = QPlainTextEdit()
        self.save_button = QPushButton(tr("screen.save", language))
        self.validate_button = QPushButton(tr("screen.validate", language))
        self.run_button = QPushButton(tr("screen.run", language))
        self.save_button.clicked.connect(self._save)
        self.validate_button.clicked.connect(self._validate)
        self.run_button.clicked.connect(self._run)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.results = ResultsPanel(language, dialogs.open_path)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel(tr("screen.configs", language)))
        left_layout.addWidget(self.configs)
        for button in (self.new_button, self.duplicate_button, self.refresh_button):
            left_layout.addWidget(button)
        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.addWidget(self.editor)
        row = QHBoxLayout()
        for button in (self.save_button, self.validate_button, self.run_button):
            row.addWidget(button)
        centre_layout.addLayout(row)
        centre_layout.addWidget(self.message)
        splitter = QSplitter()
        for part in (left, centre, self.results):
            splitter.addWidget(part)
        splitter.setSizes([220, 480, 580])  # configs narrow, editor and results wide
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self._enable()

    # ------------------------------------------------------------------------ actions
    def refresh(self) -> None:
        """Reload the list of configs."""
        try:
            entries = self.model.refresh()
        except AppError:
            self.message.setText(tr("screen.no_workspace", self.language))
            return
        self.configs.clear()
        for entry in entries:
            mark = "" if entry.valid else "  ⚠"
            item = QListWidgetItem(f"{entry.path.name}{mark}")
            item.setData(256, str(entry.path))
            item.setToolTip(entry.error or str(entry.kind))
            self.configs.addItem(item)
        self._enable()

    def _selected(self, item: QListWidgetItem) -> None:
        self.editor.setPlainText(self.model.select(Path(str(item.data(256)))))
        self.results.show_result(self.model.result)
        self.message.setText("")
        self._enable()

    def _new(self) -> None:
        kinds = self.model.kind_names
        kind = (
            kinds[0]
            if len(kinds) == 1
            else self.dialogs.ask_choice(tr("screen.kind", self.language), kinds)
        )
        name = None if kind is None else self.dialogs.ask_text(tr("screen.new_name", self.language))
        if kind is None or name is None:
            return
        self._guard(lambda: self.model.new_from_template(kind, name))

    def _duplicate(self) -> None:
        name = self.dialogs.ask_text(tr("screen.new_name", self.language))
        if name is not None:
            self._guard(lambda: self.model.duplicate(name))

    def _guard(self, action: Callable[[], object]) -> None:
        try:
            action()
        except AppError as exc:
            self.message.setText(str(exc))
            return
        self.refresh()
        self.editor.setPlainText(self.model.text)
        self.results.show_result(self.model.result)

    def _save(self) -> None:
        self.model.set_text(self.editor.toPlainText())
        self.model.save()

    def _validate(self) -> None:
        self.model.set_text(self.editor.toPlainText())
        ok, message = self.model.validate()
        key = "screen.valid" if ok else "screen.invalid"
        if ok:
            name, _, kind = message.rpartition(" (")
            self.message.setText(tr(key, self.language, name=name, kind=kind.rstrip(")")))
        else:
            self.message.setText(tr(key, self.language, error=message))

    def _run(self) -> None:
        self.model.set_text(self.editor.toPlainText())
        if self.model.output_exists() and self.model.selected is not None:
            question = tr("screen.overwrite", self.language, name=self.model.selected.name)
            if not self.dialogs.confirm(question):
                return
        try:
            job = self.model.start_run()
        except AppError as exc:
            self.message.setText(str(exc))
            return
        worker = RunWorker(job)
        worker.signals.finished.connect(self._finished)
        worker.signals.failed.connect(self._failed)
        self._started = time.monotonic()
        self.timer.start()
        self._tick()
        self._enable()
        self.pool.start(worker)

    def _tick(self) -> None:
        seconds = int(time.monotonic() - self._started)
        self.message.setText(tr("screen.running", self.language, seconds=seconds))

    def _finished(self, result: object) -> None:
        self.timer.stop()
        if not isinstance(result, RunResult):  # pragma: no cover - the job returns RunResult
            self._failed(f"unexpected result {result!r}")
            return
        view = self.model.finish(result)
        self.results.show_result(view)
        if self.model.status == "done":
            self.message.setText(tr("screen.done", self.language, status=view.status))
        else:
            self.message.setText(tr("screen.failed", self.language, error=self.model.error))
        self.refresh()

    def _failed(self, message: str) -> None:
        self.timer.stop()
        self.model.fail(message)
        self.message.setText(tr("screen.failed", self.language, error=message))
        self._enable()

    def _enable(self) -> None:
        selected = self.model.selected is not None
        idle = self.model.status != "running"
        for button in (self.save_button, self.validate_button, self.duplicate_button):
            button.setEnabled(selected and idle)
        self.run_button.setEnabled(selected and idle)
        self.new_button.setEnabled(idle and self.model.workspace.root is not None)
        self.editor.setReadOnly(not idle)


class HistoryScreen(QWidget):
    """Every recorded run, newest first."""

    def __init__(self, model: HistoryViewModel, dialogs: Dialogs, language: str) -> None:
        """Build the screen."""
        super().__init__()
        self.model = model
        self.dialogs = dialogs
        self.language = language
        self.table = QTableWidget()
        self.message = QLabel("")
        self.open_button = QPushButton(tr("history.open", language))
        self.open_button.clicked.connect(self._open)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(self.open_button)
        layout.addWidget(self.message)

    def refresh(self) -> None:
        """Reload the records."""
        try:
            runs = self.model.refresh()
        except AppError:
            self.message.setText(tr("screen.no_workspace", self.language))
            return
        self.message.setText("")
        rows = [
            (r.finished, r.name, r.kind, r.status, r.configurations_tried, r.output_dir, r.error)
            for r in runs
        ]
        fill_table(self.table, tr("history.columns", self.language).split("|"), rows)

    def _open(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.model.runs):
            self.dialogs.open_path(self.model.runs[row].output_dir)


class DataScreen(QWidget):
    """Raw files with provenance, terms and age."""

    def __init__(self, model: DataViewModel, language: str) -> None:
        """Build the screen."""
        super().__init__()
        self.model = model
        self.language = language
        self.table = QTableWidget()
        self.message = QLabel("")
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(self.message)

    def refresh(self) -> None:
        """Reload the raw store listing."""
        try:
            files = self.model.refresh()
        except AppError:
            self.message.setText(tr("screen.no_workspace", self.language))
            return
        self.message.setText("")
        rows = [
            (
                f.source,
                f.dataset,
                f.retrieved_at.date().isoformat(),
                f.age_days,
                "yes" if f.latest else "",
                f.size_bytes,
                f.sha256[:12],
                f.terms,
            )
            for f in files
        ]
        fill_table(self.table, tr("data.columns", self.language).split("|"), rows)
