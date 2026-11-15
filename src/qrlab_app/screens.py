"""The app's screens: Home, the analysis screens, Data, History and Settings."""

from __future__ import annotations

import platform
import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QTimer, qVersion
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
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
from qrlab_app.display import date_text, timestamp_text
from qrlab_app.strings import LANGUAGES, tr, tr_value
from qrlab_app.viewmodels import (
    AppError,
    DataViewModel,
    ExperimentViewModel,
    HistoryViewModel,
    SettingsViewModel,
    WorkspaceViewModel,
)
from qrlab_app.widgets import Dialogs, ResultsPanel, RunWorker, fill_table

__all__ = [
    "DataScreen",
    "ExperimentScreen",
    "HistoryScreen",
    "HomeScreen",
    "SettingsScreen",
    "app_version",
]

_PATH_ROLE = 256  # Qt.ItemDataRole.UserRole


def app_version() -> str:
    """Return the installed package version, or ``unknown`` when it is not installed."""
    try:
        return version("quant-research-lab")
    except PackageNotFoundError:  # pragma: no cover - the tests run on an installed package
        return "unknown"


class HomeScreen(QWidget):
    """Open or create a workspace; reopen a recent one."""

    def __init__(
        self,
        workspace: WorkspaceViewModel,
        settings: SettingsViewModel,
        dialogs: Dialogs,
        language: str,
        *,
        can_leave: Callable[[], bool],
        on_change: Callable[[], None],
    ) -> None:
        """Build the screen; ``can_leave`` guards a change, ``on_change`` runs after one."""
        super().__init__()
        self.workspace = workspace
        self.settings = settings
        self.dialogs = dialogs
        self.language = language
        self.can_leave = can_leave
        self.on_change = on_change
        self.path_label = QLabel(tr("home.none", language))
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.open_button = QPushButton(tr("home.open", language))
        self.create_button = QPushButton(tr("home.create", language))
        self.open_button.clicked.connect(lambda: self._choose(create=False))
        self.create_button.clicked.connect(lambda: self._choose(create=True))
        self.recent = QListWidget()
        self.recent.itemClicked.connect(self._recent_clicked)
        disclaimer = QLabel(tr("app.disclaimer", language))
        disclaimer.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(disclaimer)
        layout.addWidget(self.path_label)
        layout.addWidget(self.open_button)
        layout.addWidget(self.create_button)
        layout.addWidget(QLabel(tr("home.recent", language)))
        layout.addWidget(self.recent)
        layout.addWidget(self.message)
        self.refresh_recent()

    def refresh_recent(self) -> None:
        """List the recent workspaces; missing folders are greyed out and cannot be opened."""
        self.recent.clear()
        for entry in self.settings.recent():
            text = str(entry.path)
            item = QListWidgetItem(
                text if entry.exists else tr("home.missing", self.language, path=text)
            )
            item.setData(_PATH_ROLE, text)
            if not entry.exists:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.recent.addItem(item)

    def show_workspace(self) -> None:
        """Show the open workspace's path."""
        self.path_label.setText(tr("home.current", self.language, path=self.workspace.require()))

    def open_folder(self, folder: Path, *, create: bool = False) -> None:
        """Open (or create) ``folder`` after the other screens agree to leave."""
        if not self.can_leave():
            return
        try:
            self.workspace.create(folder) if create else self.workspace.open(folder)
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        assert self.workspace.root is not None  # set by open or create
        self.settings.remember(self.workspace.root)
        self.message.setText("")
        self.show_workspace()
        self.refresh_recent()
        self.on_change()

    def _choose(self, *, create: bool) -> None:
        key = "home.create" if create else "home.open"
        folder = self.dialogs.pick_folder(tr(key, self.language))
        if folder is not None:
            self.open_folder(folder, create=create)

    def _recent_clicked(self, item: QListWidgetItem) -> None:
        if item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.open_folder(Path(str(item.data(_PATH_ROLE))))


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
        self._loading = False
        self.configs = QListWidget()
        self.configs.itemClicked.connect(self._selected)
        self.new_button = QPushButton(tr("screen.new", language))
        self.duplicate_button = QPushButton(tr("screen.duplicate", language))
        self.refresh_button = QPushButton(tr("screen.refresh", language))
        self.new_button.clicked.connect(self._new)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.refresh_button.clicked.connect(self.refresh)
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.textChanged.connect(self._edited)
        self.save_button = QPushButton(tr("screen.save", language))
        self.validate_button = QPushButton(tr("screen.validate", language))
        self.run_button = QPushButton(tr("screen.run", language))
        self.save_button.clicked.connect(self._save)
        self.validate_button.clicked.connect(self._validate)
        self.run_button.clicked.connect(self._run)
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.save_shortcut.activated.connect(self._save)
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
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        self.configs.clear()
        for entry in entries:
            mark = "" if entry.valid else "  ⚠"
            item = QListWidgetItem(f"{entry.path.name}{mark}")
            item.setData(_PATH_ROLE, str(entry.path))
            item.setToolTip(entry.error or str(entry.kind))
            self.configs.addItem(item)
            if entry.path == self.model.selected:
                self.configs.setCurrentItem(item)
        self._enable()

    def open_config(self, path: Path) -> None:
        """Show ``path`` in the editor (a config another screen created)."""
        if not self.confirm_discard():
            return
        self.refresh()
        self._show_text(self.model.select(path))
        self.results.show_result(self.model.result)
        self.message.setText("")
        self.refresh()

    def reset(self) -> None:
        """Forget the selection and reload (another workspace was opened)."""
        self.model.clear()
        self._show_text("")
        self.results.show_result(None)
        self.message.setText("")
        self.refresh()

    def confirm_discard(self) -> bool:
        """Ask what to do with unsaved edits; ``False`` means the user cancelled."""
        if not self.model.dirty or self.model.selected is None:
            return True
        answer = self.dialogs.ask_save(
            tr("screen.unsaved", self.language, name=self.model.selected.name)
        )
        if answer == "save":
            self.model.save()
        elif answer == "discard":
            self._show_text(self.model.revert())
        return answer is not None

    def _show_text(self, text: str) -> None:
        self._loading = True
        self.editor.setPlainText(text)
        self._loading = False

    def _edited(self) -> None:
        if not self._loading:
            self.model.set_text(self.editor.toPlainText())

    def _selected(self, item: QListWidgetItem) -> None:
        path = Path(str(item.data(_PATH_ROLE)))
        if path == self.model.selected:
            return
        if not self.confirm_discard():
            self.refresh()  # the highlight goes back to the config being edited
            return
        self._show_text(self.model.select(path))
        self.results.show_result(self.model.result)
        self.message.setText("")
        self._enable()

    def _new(self) -> None:
        if not self.confirm_discard():
            return
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
        if not self.confirm_discard():
            return
        name = self.dialogs.ask_text(tr("screen.new_name", self.language))
        if name is not None:
            self._guard(lambda: self.model.duplicate(name))

    def _guard(self, action: Callable[[], object]) -> None:
        try:
            action()
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        self.refresh()
        self._show_text(self.model.text)
        self.results.show_result(self.model.result)

    def _save(self) -> None:
        if self.model.selected is not None and self.model.status != "running":
            self.model.save()

    def _validate(self) -> None:
        ok, message = self.model.validate()
        if ok:
            name, _, kind = message.rpartition(" (")
            text = tr("screen.valid", self.language, name=name, kind=kind.rstrip(")"))
        else:
            text = tr("screen.invalid", self.language, error=message)
        self.message.setText(text)

    def _run(self) -> None:
        if self.model.output_exists() and self.model.selected is not None:
            question = tr("screen.overwrite", self.language, name=self.model.selected.name)
            if not self.dialogs.confirm(question):
                return
        try:
            job = self.model.start_run()
        except AppError as exc:
            self.message.setText(exc.text(self.language))
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
            status = tr_value("status", view.status, self.language)
            self.message.setText(tr("screen.done", self.language, status=status))
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
        self.editor.setReadOnly(not idle or not selected)


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
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        self.message.setText("")
        lang = self.language
        rows = [
            (
                timestamp_text(r.finished, lang),
                r.name,
                r.kind,
                tr_value("status", r.status, lang),
                r.configurations_tried,
                r.output_dir,
                r.error,
            )
            for r in runs
        ]
        fill_table(self.table, tr("history.columns", lang).split("|"), rows, lang)

    def _open(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.model.runs):
            self.dialogs.open_path(self.model.runs[row].output_dir)


class DataScreen(QWidget):
    """Raw files with provenance, terms and age; files downloaded by hand are imported here."""

    def __init__(self, model: DataViewModel, dialogs: Dialogs, language: str) -> None:
        """Build the screen."""
        super().__init__()
        self.model = model
        self.dialogs = dialogs
        self.language = language
        self.table = QTableWidget()
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.import_button = QPushButton(tr("data.import", language))
        self.import_button.clicked.connect(self._import)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(self.import_button)
        layout.addWidget(self.message)

    def _import(self) -> None:
        path = self.dialogs.pick_file(tr("data.import", self.language))
        dataset = None if path is None else self.dialogs.ask_text(tr("data.dataset", self.language))
        if path is None or dataset is None:
            return
        try:
            self.model.import_file(path, dataset)
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        self.refresh()
        self.message.setText(
            tr("data.imported", self.language, name=path.name, dataset=dataset.strip())
        )

    def refresh(self) -> None:
        """Reload the raw store listing."""
        try:
            files = self.model.refresh()
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        lang = self.language
        rows = [
            (
                f.source,
                f.dataset,
                date_text(f.retrieved_at.date(), lang),
                f.age_days,
                tr("data.latest", lang) if f.latest else "",
                f.size_bytes,
                f.sha256[:12],
                f.terms,
            )
            for f in files
        ]
        fill_table(self.table, tr("data.columns", lang).split("|"), rows, lang)


class SettingsScreen(QWidget):
    """Language, recent workspaces and information about the app."""

    def __init__(
        self,
        settings: SettingsViewModel,
        language: str,
        *,
        settings_file: str,
        on_language: Callable[[str], bool],
        on_recent_change: Callable[[], None],
    ) -> None:
        """Build the screen.

        ``on_language`` applies a new language and returns ``False`` when it was refused.
        """
        super().__init__()
        self.settings = settings
        self.language = language
        self.on_language = on_language
        self.on_recent_change = on_recent_change
        self.languages = QComboBox()
        for code in LANGUAGES:
            self.languages.addItem(tr(f"language.{code}", language), code)
        self.languages.setCurrentIndex(LANGUAGES.index(language))
        self.languages.currentIndexChanged.connect(self._language_chosen)
        self.recent = QListWidget()
        self.remove_button = QPushButton(tr("settings.remove", language))
        self.clear_button = QPushButton(tr("settings.clear", language))
        self.remove_button.clicked.connect(self._remove)
        self.clear_button.clicked.connect(self._clear)
        self.about = QLabel(
            tr(
                "settings.version",
                language,
                version=app_version(),
                python=platform.python_version(),
                qt=qVersion(),
            )
        )
        self.file_label = QLabel(tr("settings.file", language, path=settings_file))
        self.file_label.setWordWrap(True)
        disclaimer = QLabel(tr("app.disclaimer", language))
        disclaimer.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.clear_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("settings.language", language)))
        layout.addWidget(self.languages)
        layout.addWidget(QLabel(tr("settings.recent", language)))
        layout.addWidget(self.recent)
        layout.addLayout(buttons)
        layout.addWidget(QLabel(tr("settings.about", language)))
        layout.addWidget(self.about)
        layout.addWidget(disclaimer)
        layout.addWidget(self.file_label)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        """List the recent workspaces."""
        self.recent.clear()
        for entry in self.settings.recent():
            text = str(entry.path)
            item = QListWidgetItem(
                text if entry.exists else tr("home.missing", self.language, path=text)
            )
            item.setData(_PATH_ROLE, text)
            self.recent.addItem(item)

    def _language_chosen(self, index: int) -> None:
        code = str(self.languages.itemData(index))
        if code != self.language and not self.on_language(code):
            self.languages.blockSignals(True)
            self.languages.setCurrentIndex(LANGUAGES.index(self.language))
            self.languages.blockSignals(False)

    def _remove(self) -> None:
        item = self.recent.currentItem()
        if item is not None:
            self.settings.forget(Path(str(item.data(_PATH_ROLE))))
            self.refresh()
            self.on_recent_change()

    def _clear(self) -> None:
        self.settings.clear_recent()
        self.refresh()
        self.on_recent_change()
