"""The app's screens: Home, the analysis screens, Data, Queue, History and Settings."""

from __future__ import annotations

import platform
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import Qt, qVersion
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qrlab_app.display import date_text, timestamp_text
from qrlab_app.form import FormModel
from qrlab_app.form_widgets import FormView
from qrlab_app.runs import ACTIVE, CANCELLED, RUNNING, WAITING, QueueEntry, RunQueue
from qrlab_app.strings import LANGUAGES, tr, tr_value
from qrlab_app.viewmodels import (
    AppError,
    DataViewModel,
    ExperimentViewModel,
    HistoryViewModel,
    SettingsViewModel,
    WorkspaceViewModel,
)
from qrlab_app.widgets import Dialogs, ResultsPanel, fill_table

__all__ = [
    "DataScreen",
    "ExperimentScreen",
    "HistoryScreen",
    "HomeScreen",
    "QueueScreen",
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
    """Configs of some kinds, the Form and TOML tabs with Validate and Run, and the results.

    Both tabs edit the same text (design 12.1b). Opening the Form tab reads the text; a text
    the form cannot show stays in the TOML tab with the reason. Every change in the form writes
    the text again, as TOML without comments: saving it asks first when the file has comments.
    """

    FORM_TAB = 0
    TOML_TAB = 1

    def __init__(
        self,
        model: ExperimentViewModel,
        dialogs: Dialogs,
        language: str,
        queue: RunQueue,
        on_queue: Callable[[list[QueueEntry]], None],
    ) -> None:
        """Build the screen around its view-model.

        *Run* adds the selected config to ``queue`` (design 12.2b); ``on_queue`` is called
        with the entries this screen changed, so the window can start the next run.
        """
        super().__init__()
        self.model = model
        self.dialogs = dialogs
        self.language = language
        self.queue = queue
        self.on_queue = on_queue
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
        self.form = FormView(language, dialogs.pick_file, self._form_changed)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.form, tr("screen.form", language))
        self.tabs.addTab(self.editor, tr("screen.toml", language))
        self.tabs.currentChanged.connect(self._tab_changed)
        self.save_button = QPushButton(tr("screen.save", language))
        self.validate_button = QPushButton(tr("screen.validate", language))
        self.run_button = QPushButton(tr("screen.run", language))
        self.cancel_button = QPushButton(tr("screen.cancel", language))
        self.save_button.clicked.connect(self._save)
        self.validate_button.clicked.connect(self._validate)
        self.run_button.clicked.connect(self._run)
        self.cancel_button.clicked.connect(self._cancel)
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.save_shortcut.activated.connect(self._save)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.results = ResultsPanel(language, dialogs.open_path)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel(tr("screen.configs", language)))
        left_layout.addWidget(self.configs)
        for button in (self.new_button, self.duplicate_button, self.refresh_button):
            left_layout.addWidget(button)
        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.addWidget(self.tabs)
        row = QHBoxLayout()
        for button in (self.save_button, self.validate_button, self.run_button):
            row.addWidget(button)
        row.addWidget(self.cancel_button)
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
        self.message.setText("")
        self._show_text(self.model.select(path))
        self.results.show_result(self.model.result)
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
            if not self._may_save():
                return False
            self.model.save()
        elif answer == "discard":
            self._show_text(self.model.revert())
        return answer is not None

    def _show_text(self, text: str) -> None:
        self._loading = True
        self.editor.setPlainText(text)
        self._loading = False
        if self.tabs.currentIndex() == self.FORM_TAB:
            self._load_form()

    def _load_form(self) -> None:
        """Show the text in the form, or go to the TOML tab with the reason it cannot."""
        if self.model.selected is None:
            self.form.show_model(None)
            return
        try:
            form = FormModel.from_text(self.model.text, self.model.kinds)
        except AppError as exc:
            self.form.show_model(None)
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self.TOML_TAB)
            self.tabs.blockSignals(False)
            self.message.setText(exc.text(self.language))
            return
        self.form.show_model(form, self.model.selected)

    def _tab_changed(self, index: int) -> None:
        if index == self.FORM_TAB:
            self.message.setText("")
            self._load_form()

    def _form_changed(self) -> None:
        form = self.form.model
        assert form is not None  # the form changes only while it shows a config
        self.model.set_form_text(form.to_text())
        self._loading = True
        self.editor.setPlainText(self.model.text)
        self._loading = False

    def _may_save(self) -> bool:
        """Ask before a save that drops the file's comments; ``False`` means do not save."""
        if not self.model.loses_comments or self.model.selected is None:
            return True
        name = self.model.selected.name
        return self.dialogs.confirm(tr("screen.comments", self.language, name=name))

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
        self.message.setText("")
        self._show_text(self.model.select(path))
        self.results.show_result(self.model.result)
        self.show_state()

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
        if self.model.selected is not None and not self._active() and self._may_save():
            self.model.save()

    def _validate(self) -> None:
        if not self._may_save():
            return
        ok, message = self.model.validate()
        if ok:
            name, _, kind = message.rpartition(" (")
            text = tr("screen.valid", self.language, name=name, kind=kind.rstrip(")"))
        else:
            text = tr("screen.invalid", self.language, error=message)
        self.message.setText(text)

    def _run(self) -> None:
        if not self._may_save():
            return
        if self.model.output_exists() and self.model.selected is not None:
            question = tr("screen.overwrite", self.language, name=self.model.selected.name)
            if not self.dialogs.confirm(question):
                return
        try:
            entry = self.queue.add(self.model.prepare_run())
        except AppError as exc:
            self.model.status = "idle"
            self.message.setText(exc.text(self.language))
            self._enable()
            return
        self.on_queue([entry])

    def _cancel(self) -> None:
        entry = self._entry()
        if entry is not None and entry.state in ACTIVE:
            self.queue.cancel(entry)
            self.on_queue([entry])

    # ------------------------------------------------------------------------ the queue
    def queue_changed(self, changed: list[QueueEntry]) -> None:
        """Follow the queue: show how a run of the selected config ended, or its state."""
        selected = self.model.selected
        ended = [e for e in changed if e.state not in ACTIVE and e.kind in self.model.kind_names]
        for entry in ended:
            if entry.config == selected:
                self._ended(entry)
        if ended:
            self.refresh()
        self.show_state()

    def show_state(self) -> None:
        """Show the place in line, or the seconds run, of the selected config's entry."""
        entry = self._entry()
        if entry is not None and entry.state == WAITING:
            self.model.status = WAITING
            position = self.queue.position(entry)
            self.message.setText(tr("screen.waiting", self.language, position=position))
        elif entry is not None and entry.state == RUNNING:
            self.model.status = RUNNING
            seconds = self.queue.elapsed(entry)
            self.message.setText(tr("screen.running", self.language, seconds=seconds))
        self._enable()

    def _ended(self, entry: QueueEntry) -> None:
        if entry.result is not None:
            view = self.model.finish(entry.result)
            self.results.show_result(view)
            if self.model.status == "done":
                status = tr_value("status", view.status, self.language)
                text = tr("screen.done", self.language, status=status)
                text = f"{text} {entry.note_text(self.language)}".strip()  # e.g. cancelled too late
            else:
                text = tr("screen.failed", self.language, error=self.model.error)
            self.message.setText(text)
        elif entry.state == CANCELLED:
            self.model.status = CANCELLED
            self.message.setText(entry.note_text(self.language))
        else:
            self.model.fail(entry.note_text(self.language))
            self.message.setText(tr("screen.failed", self.language, error=self.model.error))

    def _entry(self) -> QueueEntry | None:
        selected = self.model.selected
        return None if selected is None else self.queue.latest(selected)

    def _active(self) -> bool:
        entry = self._entry()
        return entry is not None and entry.state in ACTIVE

    def _enable(self) -> None:
        selected = self.model.selected is not None
        idle = not self._active()
        for button in (self.save_button, self.validate_button, self.duplicate_button):
            button.setEnabled(selected and idle)
        self.run_button.setEnabled(selected and idle)
        self.cancel_button.setEnabled(not idle)
        self.new_button.setEnabled(self.model.workspace.root is not None)
        self.editor.setReadOnly(not idle or not selected)
        self.form.setEnabled(idle and selected)


class QueueScreen(QWidget):
    """The session's runs: waiting, running and finished, with *Cancel* (design 12.2b)."""

    def __init__(
        self,
        queue: RunQueue,
        dialogs: Dialogs,
        language: str,
        on_queue: Callable[[list[QueueEntry]], None],
    ) -> None:
        """Build the screen; ``on_queue`` is called with the entries it cancelled."""
        super().__init__()
        self.queue = queue
        self.dialogs = dialogs
        self.language = language
        self.on_queue = on_queue
        self.table = QTableWidget()
        self.cancel_button = QPushButton(tr("queue.cancel", language))
        self.open_button = QPushButton(tr("queue.open", language))
        self.clear_button = QPushButton(tr("queue.clear", language))
        self.cancel_button.clicked.connect(self._cancel)
        self.open_button.clicked.connect(self._open)
        self.clear_button.clicked.connect(self._clear)
        buttons = QHBoxLayout()
        for button in (self.cancel_button, self.open_button, self.clear_button):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(buttons)

    def refresh(self) -> None:
        """Show every entry with its state, time and note; the selected row stays."""
        row = self.table.currentRow()
        lang = self.language
        rows = [
            (
                e.number,
                e.config.name,
                e.kind,
                tr_value("state", e.state, lang),
                self.queue.elapsed(e),
                e.note_text(lang),
            )
            for e in self.queue.entries
        ]
        fill_table(self.table, tr("queue.columns", lang).split("|"), rows, lang)
        if 0 <= row < len(rows):
            self.table.setCurrentCell(row, 0)

    def _selected(self) -> QueueEntry | None:
        row = self.table.currentRow()
        return self.queue.entries[row] if 0 <= row < len(self.queue.entries) else None

    def _cancel(self) -> None:
        entry = self._selected()
        if entry is not None and entry.state in ACTIVE:
            self.queue.cancel(entry)
            self.on_queue([entry])

    def _open(self) -> None:
        entry = self._selected()
        if entry is not None and entry.output_dir.is_dir():
            self.dialogs.open_path(entry.output_dir)

    def _clear(self) -> None:
        self.queue.clear_finished()
        self.refresh()


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
