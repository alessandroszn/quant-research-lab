"""Off-screen smoke test: build the window, visit every screen, run one experiment end to end."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QCoreApplication, QModelIndex, Qt, QThreadPool
from PySide6.QtWidgets import QApplication

from qrlab.data.provenance import Provenance
from qrlab.data.store import RawStore
from qrlab.experiments import RunResult
from qrlab.experiments.kinds import KINDS
from qrlab_app.app import main as app_main
from qrlab_app.main_window import ANALYSIS_SCREENS, MainWindow
from qrlab_app.screens import ExperimentScreen
from qrlab_app.viewmodels import ResultView, TableView
from qrlab_app.widgets import Dialogs, FrameModel, ResultsPanel, RunWorker

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
        self.opened: list[Path] = []

    def dialogs(self) -> Dialogs:
        def ask_choice(prompt: str, options: Sequence[str]) -> str | None:
            return self.choice

        def confirm(question: str) -> bool:
            self.confirmed.append(question)
            return self.confirm_answer

        return Dialogs(
            pick_folder=lambda title: self.folder,
            ask_text=lambda prompt: self.texts.pop(0),
            ask_choice=ask_choice,
            confirm=confirm,
            open_path=self.opened.append,
        )


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


def _window(user: FakeUser, pool: QThreadPool) -> MainWindow:
    return MainWindow(
        kinds=KINDS,
        dialogs=user.dialogs(),
        language="en",
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
    assert window.navigation.count() == 3 + len(ANALYSIS_SCREENS)
    # Before a workspace is open every screen says so.
    portfolio, projections, backtests = window.analysis
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
    window.navigation.setCurrentRow(window.navigation.count() - 1)
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
    assert backtests.message.text().startswith("ValidationError")
    user.texts = ["mine"]
    backtests.duplicate_button.click()
    assert backtests.message.text() == "mine.toml already exists"
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
    screen = window.analysis[1]
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
    model = FrameModel(pd.DataFrame({"x": [0.123456789, None]}, index=["a", "b"]))
    assert (model.rowCount(), model.columnCount()) == (2, 2)
    assert model.data(model.index(0, 1)) == "0.123457"
    assert model.data(model.index(1, 1)) == "nan"
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
    assert panel.tabs.tabText(0) == "t [in_sample]"
    panel.report_button.click()
    assert opened == [report]
    panel.show_result(None)
    panel._open_report()
    panel._open_folder()
    assert opened == [report]
