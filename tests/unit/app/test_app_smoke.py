"""Off-screen smoke test: build the window, visit every screen, run one experiment end to end."""

from __future__ import annotations

import hashlib
import json
import time
import tomllib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from PySide6.QtCore import QCoreApplication, QModelIndex, QSettings, Qt, QThreadPool
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QTableWidget

from qrlab.data.provenance import Provenance
from qrlab.data.store import RawStore
from qrlab.experiments import RunResult
from qrlab.experiments.kinds import KINDS
from qrlab.instruments import INSTRUMENT_FIELDS
from qrlab.portfolio import NATIVE_COLUMNS
from qrlab_app.app import main as app_main
from qrlab_app.form import FormModel
from qrlab_app.main_window import ANALYSIS_SCREENS, AppShell, MainWindow
from qrlab_app.portfolio_screen import KIND_COLUMN
from qrlab_app.screens import ExperimentScreen
from qrlab_app.viewmodels import ResultView, SettingsViewModel, TableView, has_comments
from qrlab_app.widgets import Dialogs, FrameModel, QtSettingsStore, ResultsPanel, RunWorker

ROOT = Path(__file__).parents[3]
PROJECTION = ROOT / "configs" / "experiments" / "example_projection.toml"


class FakeUser:
    """Answers every dialog from preset values and records what was opened."""

    def __init__(self, folder: Path | None) -> None:
        self.folder = folder
        self.texts: list[str | None] = []
        self.choice: str | None = None
        self.confirm_answer = True
        self.confirmed: list[str] = []
        self.save_answer: str | None = "save"
        self.asked_save: list[str] = []
        self.informed: list[str] = []
        self.opened: list[Path] = []
        self.file: Path | None = None

    def dialogs(self) -> Dialogs:
        def ask_choice(prompt: str, options: Sequence[str]) -> str | None:
            return self.choice

        def confirm(question: str) -> bool:
            self.confirmed.append(question)
            return self.confirm_answer

        def ask_save(question: str) -> str | None:
            self.asked_save.append(question)
            return self.save_answer

        return Dialogs(
            pick_folder=lambda title: self.folder,
            ask_text=lambda prompt: self.texts.pop(0),
            ask_choice=ask_choice,
            confirm=confirm,
            ask_save=ask_save,
            inform=self.informed.append,
            open_path=self.opened.append,
            pick_file=lambda title: self.file,
        )


class MemoryStore:
    """Settings kept in a dict."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.entries = dict(values or {})

    def get(self, key: str) -> str | None:
        return self.entries.get(key)

    def set(self, key: str, value: str) -> None:
        self.entries[key] = value


def _workspace(tmp: Path) -> Path:
    root = tmp / "ws"
    (root / "configs").mkdir(parents=True)
    text = PROJECTION.read_text(encoding="utf-8").replace("paths = 5000", "paths = 50")
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    text = text[:start] + 'directory = "../results/projection"' + text[end + 1 :]
    (root / "configs" / "projection.toml").write_text(text, encoding="utf-8")
    content = b"raw"
    RawStore(root / "data").put(
        content,
        Provenance(
            source="ecb",
            dataset="fx",
            url="https://example.org/fx.zip",
            retrieved_at=datetime(2026, 11, 10, tzinfo=UTC),
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            terms="t",
        ),
    )
    return root


def _settings(store: MemoryStore | None = None, system: str = "en_GB") -> SettingsViewModel:
    return SettingsViewModel(store if store is not None else MemoryStore(), system_language=system)


def _window(
    user: FakeUser, pool: QThreadPool, settings: SettingsViewModel | None = None
) -> MainWindow:
    return MainWindow(
        kinds=KINDS,
        dialogs=user.dialogs(),
        settings=settings if settings is not None else _settings(),
        now=lambda: datetime(2026, 11, 12, tzinfo=UTC),
        pool=pool,
    )


def _wait(screen: ExperimentScreen, pool: QThreadPool) -> None:
    assert pool.waitForDone(120_000)
    deadline = time.monotonic() + 30
    while screen.model.status == "running" and time.monotonic() < deadline:
        QCoreApplication.processEvents()
    assert screen.model.status != "running"


def test_window_screens_and_a_full_run(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    user = FakeUser(root)
    pool = QThreadPool()
    window = _window(user, pool)
    assert window.navigation.count() == 5 + len(ANALYSIS_SCREENS)  # Home, Portfolios, Data, …
    # Before a workspace is open every screen says so.
    portfolio = window.screen_for("portfolio_report")
    projections = window.screen_for("projection")
    backtests = window.screen_for("backtest")
    assert window.screen_for("risk_report") is not window.screen_for("optimisation")
    with pytest.raises(KeyError):
        window.screen_for("nope")
    projections.refresh()
    assert "Open a workspace first" in projections.message.text()
    window.data.refresh()
    window.history.refresh()
    assert "Open a workspace first" in window.history.message.text()

    window.home.open_button.click()
    assert str(root) in window.home.path_label.text()
    for row in range(window.navigation.count()):
        window.navigation.setCurrentRow(row)
        assert window.stack.currentIndex() == row
    assert window.data.table.rowCount() == 1

    # Select, validate and run the projection.
    assert projections.configs.count() == 1
    projections.configs.itemClicked.emit(projections.configs.item(0))
    assert 'kind = "projection"' in projections.editor.toPlainText()
    projections.validate_button.click()
    assert projections.message.text() == "Valid: example-savings-projection (projection)."
    projections.save_button.click()
    projections.run_button.click()
    assert not projections.run_button.isEnabled()  # running
    _wait(projections, pool)
    assert projections.model.status == "done"
    assert projections.message.text() == "Finished: success."
    assert projections.results.tabs.count() >= 3  # tables, scalars, figures
    projections.results.folder_button.click()
    assert user.opened[-1] == root / "results" / "projection"
    assert not projections.results.report_button.isEnabled()

    # A second run asks before replacing the outputs; "no" keeps them.
    user.confirm_answer = False
    projections.run_button.click()
    assert user.confirmed
    assert projections.model.status == "done"
    user.confirm_answer = True
    projections.run_button.click()
    _wait(projections, pool)
    assert projections.model.status == "done"

    # History shows the run and opens its folder.
    window.navigation.setCurrentRow(0)
    window.navigation.setCurrentRow(window.navigation.count() - 2)  # History
    assert window.history.table.rowCount() == 1
    window.history.table.setCurrentCell(0, 0)
    window.history.open_button.click()
    assert user.opened[-1] == root / "results" / "projection"
    opened = len(user.opened)
    window.history.table.setCurrentCell(-1, -1)
    window.history.open_button.click()
    assert len(user.opened) == opened

    # A config from the template is invalid until filled in; the error is shown.
    user.choice = "backtest"
    user.texts = ["mine"]
    backtests.new_button.click()
    assert backtests.model.selected == root / "configs" / "mine.toml"
    backtests.validate_button.click()
    assert backtests.message.text().startswith("Not valid: ValidationError")
    backtests.run_button.click()
    assert backtests.message.text().startswith("Not valid: ValidationError")
    user.texts = ["mine"]
    backtests.duplicate_button.click()
    assert backtests.message.text() == "mine.toml already exists."
    user.texts = [None]
    backtests.duplicate_button.click()
    user.choice = None
    backtests.new_button.click()
    portfolio.refresh()
    assert portfolio.configs.count() == 0
    window.close()


def test_home_errors_and_cancel(qapp: QApplication, tmp_path: Path) -> None:
    user = FakeUser(tmp_path / "missing")
    window = _window(user, QThreadPool())
    window.home.open_button.click()
    assert "is not a folder" in window.home.message.text()
    user.folder = None
    window.home.create_button.click()
    assert window.workspace.root is None
    user.folder = tmp_path / "new"
    window.home.create_button.click()
    assert (tmp_path / "new" / "configs").is_dir()
    window.close()


def test_worker_reports_failures(qapp: QApplication) -> None:
    errors: list[str] = []

    def boom() -> object:
        raise ValueError("boom")

    worker = RunWorker(boom)
    worker.signals.failed.connect(errors.append)
    worker.run()
    QCoreApplication.processEvents()
    assert errors == ["ValueError: boom"]
    results: list[object] = []
    ok = RunWorker(lambda: 42)
    ok.signals.finished.connect(results.append)
    ok.run()
    QCoreApplication.processEvents()
    assert results == [42]
    assert callable(app_main)


def test_screen_handles_a_worker_failure(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    user = FakeUser(root)
    window = _window(user, QThreadPool())
    window.home.open_button.click()
    screen = window.screen_for("projection")
    screen.configs.itemClicked.emit(screen.configs.item(0))
    screen.model.status = "running"
    screen._failed("RuntimeError: lost")
    assert screen.model.status == "failed"
    assert screen.message.text() == "Failed: RuntimeError: lost"
    folder = root / "results" / "failed"
    folder.mkdir(parents=True)
    record = {"status": "failure", "error": "ValidationError: x", "outputs": {}, "scalars": {}}
    (folder / "record.json").write_text(json.dumps(record), encoding="utf-8")
    screen.model.status = "running"
    screen._finished(RunResult(folder, record))
    assert screen.message.text() == "Failed: ValidationError: x"
    window.close()


def test_frame_model_and_results_panel(qapp: QApplication, tmp_path: Path) -> None:
    model = FrameModel(pd.DataFrame({"x": [0.123456789, None]}, index=["a", "b"]), "en")
    assert (model.rowCount(), model.columnCount()) == (2, 2)
    assert model.data(model.index(0, 1)) == "0.123457"
    assert model.data(model.index(1, 1)) == "—"
    assert model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole) is None
    assert model.data(QModelIndex()) is None
    assert model.headerData(0, Qt.Orientation.Horizontal) == "index"
    assert model.headerData(1, Qt.Orientation.Vertical) == "2"
    assert model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole) is None
    assert model.rowCount(model.index(0, 0)) == 0
    assert model.columnCount(model.index(0, 0)) == 0
    opened: list[Path] = []
    panel = ResultsPanel("en", opened.append)
    report = tmp_path / "report.html"
    view = ResultView(
        output_dir=tmp_path,
        status="failure",
        error="x",
        tables=(TableView("t", "in_sample", pd.DataFrame({"a": [1]})),),
        scalars=(),
        figures=(),
        report=report,
    )
    panel.show_result(view)
    assert panel.tabs.tabText(0) == "t [in-sample]"
    assert panel.notice.text() == ""
    from dataclasses import replace

    panel.show_result(replace(view, notice="Not a forecast."))
    assert panel.notice.text() == "Not a forecast."
    panel.report_button.click()
    assert opened == [report]
    panel.show_result(None)
    panel._open_report()
    panel._open_folder()
    assert opened == [report]


# ------------------------------------------------------------- 6.1c: language and settings
def _cell(table: QTableWidget, row: int, column: int) -> str:
    item = table.item(row, column)
    assert item is not None
    return item.text()


def _header(table: QTableWidget, column: int) -> str:
    item = table.horizontalHeaderItem(column)
    assert item is not None
    return item.text()


def _selected(screen: ExperimentScreen) -> Path | None:
    """Read through a call, so the type checker does not narrow it."""
    return screen.model.selected


def _shell(user: FakeUser, store: MemoryStore, pool: QThreadPool) -> AppShell:
    return AppShell(
        kinds=KINDS,
        dialogs=user.dialogs(),
        settings=_settings(store, system="it_IT"),
        now=lambda: datetime(2026, 11, 12, tzinfo=UTC),
        pool=pool,
        settings_file="C:/settings/qrlab-app.ini",
    )


def test_italian_window_and_language_switch(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    user, store = FakeUser(root), MemoryStore()
    shell = _shell(user, store, QThreadPool())
    first = shell.window
    assert first.language == "it"  # from the system locale
    assert first.navigation.item(0).text() == "Home"
    last = first.navigation.count() - 1
    assert first.navigation.item(last).text() == "Impostazioni"
    assert first.windowTitle() == "Quant Research Lab"
    first.home.open_button.click()
    assert first.windowTitle() == "Quant Research Lab — ws"
    assert "qrlab-app.ini" in first.settings_screen.file_label.text()
    assert first.settings_screen.about.text().startswith("Quant Research Lab ")
    first.navigation.setCurrentRow(last)

    # During a run the language cannot change: the user is told and the choice is undone.
    first.screen_for("projection").model.status = "running"
    first.settings_screen.languages.setCurrentIndex(0)  # English
    assert user.informed == ["Non si può cambiare lingua durante un'esecuzione."]
    assert shell.window is first
    assert first.settings_screen.languages.currentData() == "it"
    assert store.entries.get("language") is None
    first.screen_for("projection").model.status = "idle"

    # Otherwise the window is rebuilt in English, on the same screen and workspace.
    first.settings_screen.languages.setCurrentIndex(0)
    second = shell.window
    assert second is not first
    assert store.entries["language"] == "en"
    assert second.navigation.item(last).text() == "Settings"
    assert second.navigation.currentRow() == last
    assert second.workspace.root == root
    assert "ws" in second.home.path_label.text()
    assert second.screen_for("projection").configs.count() == 1
    assert "window_geometry" in store.entries
    second.close()

    # Before any workspace, with the window on screen: the new window is shown too.
    other = _shell(FakeUser(None), MemoryStore(), QThreadPool())
    other.window.show()
    shown = other.window
    shown.settings_screen.languages.setCurrentIndex(0)
    assert other.window is not shown
    assert other.window.isVisible()
    assert other.window.workspace.root is None
    other.window.close()

    # A window on its own saves the choice; it applies at the next start.
    alone_store = MemoryStore()
    alone = _window(FakeUser(None), QThreadPool(), _settings(alone_store))
    alone.screen_for("projection").save_shortcut.activated.emit()  # nothing selected: no-op
    alone.settings_screen.languages.setCurrentIndex(1)
    assert alone_store.entries["language"] == "it"
    assert alone.language == "en"
    alone.close()


def test_results_in_italian(qapp: QApplication, tmp_path: Path) -> None:
    frame = pd.DataFrame({"x": [0.0317, float("nan"), 1234567.891], "n": [1, 2, 2024]})
    model = FrameModel(frame, "it")
    assert [model.data(model.index(r, 1)) for r in range(3)] == ["0,0317", "—", "1.234.570"]
    assert model.data(model.index(2, 2)) == "2024"
    panel = ResultsPanel("it", lambda path: None)
    view = ResultView(
        output_dir=tmp_path,
        status="success",
        error=None,
        tables=(TableView("weights", "in_sample", frame),),
        scalars=(("p", 0.25, "out_of_sample"), ("method", "hrp", "descriptive")),
        figures=(),
        report=None,
    )
    panel.show_result(view)
    assert panel.title.text().endswith(": riuscita")
    assert panel.tabs.tabText(0) == "weights [in campione]"
    assert panel.tabs.tabText(1) == "Valori"
    scalars = panel.tabs.widget(1)
    assert isinstance(scalars, QTableWidget)
    assert _header(scalars, 2) == "Campione"
    assert [_cell(scalars, 0, c) for c in range(3)] == ["p", "0,25", "fuori campione"]
    assert _cell(scalars, 1, 1) == "hrp"


def test_data_and_history_in_italian(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    user = FakeUser(root)
    pool = QThreadPool()
    window = _window(user, pool, _settings(MemoryStore({"language": "it"})))
    window.home.open_button.click()
    window.data.refresh()
    assert _cell(window.data.table, 0, 2) == "10/11/2026"
    assert _cell(window.data.table, 0, 4) == "sì"
    assert _header(window.data.table, 0) == "Fonte"
    screen = window.screen_for("projection")
    screen.configs.itemClicked.emit(screen.configs.item(0))
    screen.run_button.click()
    _wait(screen, pool)
    assert screen.message.text() == "Esecuzione terminata: riuscita."
    window.history.refresh()
    assert _cell(window.history.table, 0, 3) == "riuscita"
    finished = _cell(window.history.table, 0, 0)
    assert finished.endswith(" UTC")
    assert finished[2] == "/"  # dd/mm/yyyy
    window.close()


def test_unsaved_edits_are_never_lost_silently(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    first_path = root / "configs" / "projection.toml"
    second_path = root / "configs" / "second.toml"
    original = first_path.read_text(encoding="utf-8")
    second_path.write_text(original, encoding="utf-8")
    user = FakeUser(root)
    window = _window(user, QThreadPool())
    window.home.open_button.click()
    screen = window.screen_for("projection")
    assert screen.editor.isReadOnly()  # nothing selected yet
    screen.configs.itemClicked.emit(screen.configs.item(0))
    assert screen.model.selected == first_path
    screen.configs.itemClicked.emit(screen.configs.item(0))  # the same config: no question
    assert user.asked_save == []
    screen.editor.setPlainText(original + "\n# edited")
    assert screen.model.dirty

    # Cancel keeps the edit and the selection.
    user.save_answer = None
    screen.configs.itemClicked.emit(screen.configs.item(1))
    assert user.asked_save == ["projection.toml has unsaved changes. Save them?"]
    assert screen.model.selected == first_path
    assert screen.editor.toPlainText().endswith("# edited")
    assert screen.configs.currentItem().text() == "projection.toml"
    screen.new_button.click()  # cancelled at the question about unsaved edits
    screen.duplicate_button.click()
    assert len(user.asked_save) == 3

    # Discard drops the edit; the file is unchanged.
    user.save_answer = "discard"
    screen.configs.itemClicked.emit(screen.configs.item(1))
    assert screen.model.selected == second_path
    assert first_path.read_text(encoding="utf-8") == original

    # Save writes the edit before moving on.
    screen.editor.setPlainText(original + "\n# second")
    user.save_answer = "save"
    screen.configs.itemClicked.emit(screen.configs.item(0))
    assert second_path.read_text(encoding="utf-8").endswith("# second")
    assert screen.model.selected == first_path

    # Ctrl+S saves; F5 reloads the screen on show.
    screen.editor.setPlainText(original + "\n# shortcut")
    screen.save_shortcut.activated.emit()
    assert first_path.read_text(encoding="utf-8").endswith("# shortcut")
    for row in range(window.navigation.count()):
        window.navigation.setCurrentRow(row)
        window.refresh_shortcut.activated.emit()

    # Opening another workspace asks first, then resets every screen.
    screen.editor.setPlainText(original + "\n# pending")
    user.save_answer = None
    other = tmp_path / "other"
    user.folder = other
    window.home.create_button.click()
    assert window.workspace.root == root  # cancelled
    user.save_answer = "discard"
    window.home.create_button.click()
    assert window.workspace.root == other
    assert _selected(screen) is None
    assert screen.editor.toPlainText() == ""
    window.close()


def test_closing_during_a_run_is_refused(qapp: QApplication, tmp_path: Path) -> None:
    store = MemoryStore()
    user = FakeUser(_workspace(tmp_path))
    window = _window(user, QThreadPool(), _settings(store))
    window.home.open_button.click()
    window.show()
    window.screen_for("projection").model.status = "running"
    assert not window.close()
    assert user.informed == [
        "A run is in progress and cannot be stopped. Wait for it to finish, then close the app."
    ]
    window.home.create_button.click()  # changing workspace is refused too
    assert user.informed[-1] == "Another run is in progress."
    window.screen_for("projection").model.status = "idle"
    window.resize(700, 500)
    assert window.close()
    assert store.entries["window_geometry"]
    reopened = _window(user, QThreadPool(), _settings(store))  # the size comes back
    assert reopened.height() == 500  # not the default 800 (offscreen, the width has a minimum)
    reopened.close()


def test_recent_workspaces_on_home_and_settings(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    gone = tmp_path / "gone"
    gone.mkdir()
    settings = _settings(MemoryStore())
    settings.remember(gone)
    gone.rmdir()
    user = FakeUser(root)
    window = _window(user, QThreadPool(), settings)
    assert window.home.recent.count() == 1
    missing = window.home.recent.item(0)
    assert missing.text().endswith("(not found)")
    window.home.recent.itemClicked.emit(missing)  # disabled: nothing happens
    assert window.workspace.root is None
    window.home.open_button.click()
    assert [r.path for r in settings.recent()] == [root.resolve(), gone.resolve()]

    reopened = _window(user, QThreadPool(), settings)
    assert reopened.home.recent.item(0).text() == str(root.resolve())
    reopened.home.recent.itemClicked.emit(reopened.home.recent.item(0))
    assert reopened.workspace.root == root.resolve()

    page = reopened.settings_screen
    assert page.recent.count() == 2
    page.recent.setCurrentRow(-1)
    page.remove_button.click()  # nothing selected: nothing removed
    assert page.recent.count() == 2
    page.recent.setCurrentRow(1)
    page.remove_button.click()
    assert [r.path for r in settings.recent()] == [root.resolve()]
    assert reopened.home.recent.count() == 1
    page.clear_button.click()
    assert settings.recent() == []
    assert reopened.home.recent.count() == 0
    window.close()
    reopened.close()


def test_settings_file_round_trip(qapp: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "qrlab-app.ini"
    store = QtSettingsStore.at(path)
    assert Path(store.file_name) == path
    assert store.get("language") is None
    settings = SettingsViewModel(store, system_language="en")
    odd = tmp_path / "Città, 2026" / "a b"
    odd.mkdir(parents=True)
    settings.remember(odd)
    settings.set_language("it")
    again = SettingsViewModel(QtSettingsStore.at(path), system_language="en")
    assert again.language == "it"
    assert [r.path for r in again.recent()] == [odd.resolve()]
    with pytest.raises(ValueError, match="INI"):
        QtSettingsStore(QSettings(str(tmp_path / "x.conf"), QSettings.Format.NativeFormat))


def test_the_full_portfolio_example_runs_in_the_app(qapp: QApplication, tmp_path: Path) -> None:
    """Two currencies, input groups, look-through and tracking, run from the app (7.4b)."""
    root = tmp_path / "ws"
    (root / "configs").mkdir(parents=True)
    full = ROOT / "configs" / "experiments" / "example_portfolio_report_full.toml"
    text = full.read_text(encoding="utf-8")
    text = text.replace('"../../', f'"{ROOT.as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    text = text[:start] + 'directory = "../results/full"' + text[end + 1 :]
    (root / "configs" / "full.toml").write_text(text, encoding="utf-8")
    user = FakeUser(root)
    pool = QThreadPool()
    window = _window(user, pool)
    window.home.open_button.click()
    portfolio = window.screen_for("portfolio_report")
    portfolio.refresh()
    assert portfolio.configs.count() == 1
    portfolio.configs.itemClicked.emit(portfolio.configs.item(0))
    portfolio.validate_button.click()
    assert portfolio.message.text().startswith("Valid: example-portfolio-report-full")
    portfolio.run_button.click()
    _wait(portfolio, pool)
    assert portfolio.message.text() == "Finished: success."
    tabs = [portfolio.results.tabs.tabText(i) for i in range(portfolio.results.tabs.count())]
    assert "exposures [descriptive]" in tabs
    assert portfolio.results.report_button.isEnabled()
    window.close()


# --------------------------------------------------------------------------- Portfolio screen
def _type(table: QTableWidget, row: int, column: int, text: str) -> None:
    """Type into a cell as a user would (the itemChanged signal reaches the view model)."""
    item = table.item(row, column)
    assert item is not None
    assert item.flags() & Qt.ItemFlag.ItemIsEditable, (row, column)
    item.setText(text)


def test_a_portfolio_built_on_the_screen(qapp: QApplication, tmp_path: Path) -> None:
    """The 8.8a starting position typed into the tables, saved, then a report config made."""
    root = _workspace(tmp_path)
    user = FakeUser(root)
    window = _window(user, QThreadPool())
    window.home.open_button.click()
    screen = window.portfolios
    window.navigation.setCurrentRow(1)
    assert window.stack.currentWidget() is screen
    assert not screen.save_button.isEnabled()
    user.texts = ["mine"]
    screen.new_button.click()
    assert [screen.portfolios.item(i).text() for i in range(screen.portfolios.count())] == ["mine"]
    assert screen.save_button.isEnabled()

    screen.add_instrument_button.click()
    fields = {
        "isin": "IE0000000012",
        "name": "Example World Equity UCITS ETF",
        "instrument_type": "etf",
        "asset_class": "equity",
        "currency": "EUR",
        "as_of": "2026-01-02",
        "source": "synthetic example",
    }
    for name, text in fields.items():
        _type(screen.instruments, 0, INSTRUMENT_FIELDS.index(name), text)
    user.texts = ["2026-01-02"]
    screen.start_button.click()
    assert screen.message.text().startswith("Added a transfer in per instrument")
    assert screen.transactions.rowCount() == 2
    column = NATIVE_COLUMNS.index
    amount = screen.transactions.item(1, column("amount"))
    assert amount is not None
    assert not amount.flags() & Qt.ItemFlag.ItemIsEditable  # a transfer in has no amount
    _type(screen.transactions, 0, column("amount"), "1000")
    _type(screen.transactions, 1, column("quantity"), "100")
    _type(screen.transactions, 1, column("price"), "50")

    screen.save_button.click()  # the cost is optional, but the deposit date is set: valid
    assert screen.message.text() == "Valid and saved: 2 transactions, 1 instruments."
    _type(screen.transactions, 1, column("quantity"), "-5")
    screen.save_button.click()
    assert screen.message.text().startswith("Transactions, row 2: line 3: negative quantity")
    assert screen.transactions.currentRow() == 1
    _type(screen.transactions, 1, column("quantity"), "100")
    _type(screen.transactions, 1, column("cost"), "40")
    screen.save_button.click()
    assert screen.message.text().startswith("Valid and saved")

    user.choice = "sell"
    screen.add_button.click()
    box = screen.transactions.cellWidget(2, KIND_COLUMN)
    assert isinstance(box, QComboBox)
    box.setCurrentText("buy")
    assert screen.model.transactions[2]["kind"] == "buy"
    screen.transactions.setCurrentCell(2, 0)
    screen.remove_button.click()
    assert screen.transactions.rowCount() == 2
    screen.tabs.setCurrentWidget(screen.instruments)
    screen.instruments.setCurrentCell(-1, -1)
    screen.remove_button.click()  # nothing selected: nothing removed
    assert screen.instruments.rowCount() == 1

    user.texts = ["mine-report"]
    screen.report_button.click()
    report = window.screen_for("portfolio_report")
    assert window.stack.currentWidget() is report
    assert report.model.selected == root / "configs" / "mine-report.toml"
    assert 'transactions_format = "native"' in report.editor.toPlainText()
    user.texts = ["mine-report"]
    screen.report_button.click()
    assert screen.message.text() == "mine-report.toml already exists."

    # A report config with unsaved edits is not replaced by a new one without asking.
    report.editor.setPlainText(report.editor.toPlainText() + "\n# my note\n")
    user.save_answer = None
    user.texts = ["other-report"]
    screen.report_button.click()
    assert report.model.selected == root / "configs" / "mine-report.toml"
    assert (root / "configs" / "other-report.toml").is_file()

    # Removing an instrument row.
    screen.tabs.setCurrentWidget(screen.instruments)
    screen.instruments.setCurrentCell(0, 0)
    screen.remove_button.click()
    assert screen.instruments.rowCount() == 0
    window.close()


def test_portfolio_screen_guards(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    user = FakeUser(root)
    window = _window(user, QThreadPool())
    screen = window.portfolios
    screen.refresh()
    assert screen.message.text() == "Open a workspace first (Home)."
    window.home.open_button.click()
    assert screen._save() is False  # no portfolio: a defensive path the buttons never reach
    assert screen.message.text() == "No portfolio is selected."
    user.texts = ["a/b"]
    screen.new_button.click()
    assert screen.message.text() == "'a/b' is not a valid file name."
    user.texts = ["first", "second"]
    screen.new_button.click()
    screen.new_button.click()
    user.texts = [None]
    screen.start_button.click()  # cancelled
    user.texts = ["2026-01-02"]
    screen.start_button.click()
    assert screen.message.text() == "Add the instruments first."
    user.choice = None
    screen.add_button.click()  # cancelled
    user.texts = [None]
    screen.report_button.click()  # cancelled
    user.texts = ["r"]
    screen.report_button.click()
    assert screen.message.text() == "Validate and save the portfolio first."
    screen.save_button.click()
    assert screen.message.text() == "Transactions: there are no transactions"

    # Unsaved edits: cancel keeps them, discard drops them, save that fails stays.
    screen.add_instrument_button.click()
    user.save_answer = None
    screen.portfolios.itemClicked.emit(screen.portfolios.item(0))
    assert screen.model.selected == "second"
    user.save_answer = "save"
    screen.portfolios.itemClicked.emit(screen.portfolios.item(0))
    assert screen.model.selected == "second"
    assert screen.message.text().startswith("Instruments, row 1:")
    user.save_answer = "discard"
    screen.portfolios.itemClicked.emit(screen.portfolios.item(0))
    assert screen.model.selected == "first"
    screen.portfolios.itemClicked.emit(screen.portfolios.item(0))  # same one: nothing to do
    (root / "portfolios" / "second" / "transactions.csv").write_text("x\n", encoding="utf-8")
    screen.portfolios.itemClicked.emit(screen.portfolios.item(1))
    assert screen.message.text().startswith("Cannot read second:")
    user.texts = [None]
    screen.new_button.click()  # cancelled
    screen.add_instrument_button.click()
    user.save_answer = None
    user.texts = ["third"]
    screen.new_button.click()  # unsaved edits, cancelled: no new portfolio
    assert "third" not in screen.model.names
    window.close()


def test_the_data_screen_imports_a_downloaded_file(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    user = FakeUser(root)
    window = _window(user, QThreadPool())
    window.home.open_button.click()
    download = tmp_path / "holdings.csv"
    download.write_bytes(b"Ticker,Name\nAAPL,APPLE\n")
    screen = window.data
    screen.import_button.click()  # no file picked: nothing happens
    user.file = download
    user.texts = [None]
    screen.import_button.click()  # no dataset name: nothing happens
    assert screen.table.rowCount() == 1
    user.texts = ["holdings-world"]
    screen.import_button.click()
    assert screen.table.rowCount() == 2
    assert screen.message.text() == (
        "holdings.csv imported as holdings-world, unchanged, with its provenance."
    )
    user.texts = ["../up"]
    screen.import_button.click()
    assert screen.message.text() == "'../up' is not a valid file name."
    window.close()


def _form_model(screen: ExperimentScreen) -> FormModel | None:
    """Return the model the form shows, read afresh."""
    return screen.form.model


def _loses_comments(screen: ExperimentScreen) -> bool:
    """Return whether saving would drop comments, read afresh."""
    return screen.model.loses_comments


def test_the_form_and_toml_tabs_edit_the_same_config(qapp: QApplication, tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    path = root / "configs" / "projection.toml"
    original = path.read_text(encoding="utf-8")
    assert has_comments(original)
    broken = root / "configs" / "unknown_key.toml"
    broken.write_text(original.replace("[parameters]", "[parameters]\nnope = 1"), "utf-8")
    user = FakeUser(root)
    window = _window(user, QThreadPool())
    window.home.open_button.click()
    screen = window.screen_for("projection")
    form_tab, toml_tab = ExperimentScreen.FORM_TAB, ExperimentScreen.TOML_TAB
    assert screen.tabs.currentIndex() == form_tab
    assert _form_model(screen) is None
    assert not screen.form.isEnabled()  # nothing selected

    # The form shows the selected config; an edit there writes the TOML tab's text.
    screen.open_config(path)
    assert screen.form.isEnabled()
    edit = screen.form.editors[("parameters", "paths")]
    assert isinstance(edit, QLineEdit)
    edit.setText("60")
    edit.textEdited.emit("60")
    assert tomllib.loads(screen.editor.toPlainText())["parameters"]["paths"] == 60
    assert screen.model.dirty
    assert _loses_comments(screen) is True

    # Saving, validating and running ask first, because the comments would be lost.
    question = "Saving from the form writes projection.toml without its comments. Save anyway?"
    user.confirm_answer = False
    screen.save_button.click()
    screen.validate_button.click()
    screen.run_button.click()
    user.save_answer = "save"
    assert not screen.confirm_discard()  # Save, then No to the comments: nothing happens
    assert user.confirmed == [question] * 4
    assert path.read_text(encoding="utf-8") == original
    user.confirm_answer = True
    screen.save_button.click()
    saved = path.read_text(encoding="utf-8")
    assert saved == screen.editor.toPlainText()
    assert not has_comments(saved)
    assert tomllib.loads(saved) == {**tomllib.loads(original), "parameters": {
        **tomllib.loads(original)["parameters"], "paths": 60}}  # fmt: skip

    # The TOML tab and back: the form reads the text as edited.
    screen.tabs.setCurrentIndex(toml_tab)
    screen.editor.setPlainText(saved.replace("paths = 60", "paths = 70"))
    screen.tabs.setCurrentIndex(form_tab)
    shown = _form_model(screen)
    assert shown is not None
    assert shown.value(("parameters", "paths")) == 70
    assert _loses_comments(screen) is False  # the saved file has no comments any more

    # Text the form cannot show stays in the TOML tab, with the reason.
    screen.tabs.setCurrentIndex(toml_tab)
    screen.editor.setPlainText("[parameters\n")
    screen.tabs.setCurrentIndex(form_tab)
    assert screen.tabs.currentIndex() == toml_tab
    assert screen.message.text().startswith("The form needs valid TOML")
    user.save_answer = "discard"
    screen.open_config(broken)  # opened in the TOML tab, where it stays
    assert screen.model.selected == broken
    screen.tabs.setCurrentIndex(form_tab)
    assert screen.tabs.currentIndex() == toml_tab
    assert screen.message.text() == (
        "The form cannot show this config, so it stays in the TOML tab: "
        "[parameters]: unknown keys ['nope']"
    )
    assert _form_model(screen) is None
    screen.reset()
    screen.tabs.setCurrentIndex(form_tab)
    assert _form_model(screen) is None
    window.close()
