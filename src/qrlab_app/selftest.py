"""``--self-test``: run every config of a workspace through the real window, without a user.

Used by the Windows build in CI to prove that the frozen program works end to end. The window
is never shown; dialogs answer automatically and settings stay in memory, so the user's own
settings file is never touched. There is no financial logic here: the self-test clicks the same
buttons a user would.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThreadPool
from PySide6.QtWidgets import QApplication

from qrlab.experiments.kinds import KINDS
from qrlab_app.main_window import MainWindow
from qrlab_app.screens import ExperimentScreen
from qrlab_app.viewmodels import SettingsViewModel
from qrlab_app.widgets import Dialogs

__all__ = ["RUN_TIMEOUT_SECONDS", "MemorySettingsStore", "self_test"]

RUN_TIMEOUT_SECONDS = 1800
"""Longest wait for one run before the self-test fails."""


class MemorySettingsStore:
    """Settings kept in memory for the duration of the self-test."""

    def __init__(self) -> None:
        """Start empty."""
        self.entries: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        """Return the stored value or ``None``."""
        return self.entries.get(key)

    def set(self, key: str, value: str) -> None:
        """Store a value."""
        self.entries[key] = value


def _automatic_dialogs(log: Callable[[str], None]) -> Dialogs:
    return Dialogs(
        pick_folder=lambda title: None,
        ask_text=lambda prompt: None,
        ask_choice=lambda prompt, options: None,
        confirm=lambda question: True,  # replace earlier outputs
        ask_save=lambda question: "discard",  # the self-test never edits a config
        inform=log,
        open_path=lambda path: None,
        pick_file=lambda title: None,
    )


def _run_one(screen: ExperimentScreen, path: Path, pool: QThreadPool) -> bool:
    for row in range(screen.configs.count()):
        item = screen.configs.item(row)
        if Path(str(item.data(256))) == path:
            screen.configs.itemClicked.emit(item)
    if screen.model.selected != path:  # pragma: no cover - every listed config is clickable
        return False
    screen.run_button.click()
    if screen.model.status != "running":  # refused before starting, e.g. an invalid config
        return False
    pool.waitForDone(RUN_TIMEOUT_SECONDS * 1000)
    deadline = time.monotonic() + 60
    while screen.model.status == "running" and time.monotonic() < deadline:
        QCoreApplication.processEvents()
    return screen.model.status == "done"


def self_test(root: Path, *, log: Callable[[str], None] = print) -> int:
    """Run every config of the workspace at ``root``; 0 only if all ran and succeeded.

    A workspace without configs fails: a self-test that tested nothing must not pass.
    """
    app = QApplication.instance()
    if app is None:  # pragma: no cover - the tests share one application
        app = QApplication([])
    pool = QThreadPool()
    window = MainWindow(
        kinds=KINDS,
        dialogs=_automatic_dialogs(log),
        settings=SettingsViewModel(MemorySettingsStore(), system_language="en"),
        now=lambda: datetime.now(UTC),
        pool=pool,
    )
    window.home.open_folder(Path(root))
    if window.workspace.root is None:
        log(f"self-test: cannot open {root}: {window.home.message.text()}")
        window.close()
        return 1
    log(f"self-test: portfolios: {window.portfolios.model.names}")
    ran = failed = 0
    for screen in window.analysis:
        for entry in list(screen.model.entries):
            ok = _run_one(screen, entry.path, pool)
            ran += 1
            failed += not ok
            log(f"self-test: {entry.path.name}: {'ok' if ok else 'FAILED'} {screen.message.text()}")
    window.close()
    if ran == 0:
        log("self-test: the workspace has no configs")
        return 1
    log(f"self-test: {ran - failed} of {ran} runs succeeded")
    return 0 if failed == 0 else 1
