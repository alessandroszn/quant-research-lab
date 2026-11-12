"""Start the desktop app (``qrlab-app``)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from PySide6.QtCore import QLocale, QThreadPool
from PySide6.QtWidgets import QApplication

from qrlab.experiments.kinds import KINDS
from qrlab_app.main_window import AppShell
from qrlab_app.viewmodels import SettingsViewModel
from qrlab_app.widgets import QtSettingsStore, default_dialogs

__all__ = ["main"]


def main() -> int:  # pragma: no cover - starts the event loop; the smoke test builds the window
    """Open the main window and run until it is closed."""
    app = QApplication(sys.argv)
    store = QtSettingsStore.for_user()
    shell = AppShell(
        kinds=KINDS,
        dialogs=default_dialogs(None),
        settings=SettingsViewModel(store, system_language=QLocale.system().name()),
        now=lambda: datetime.now(UTC),
        pool=QThreadPool.globalInstance(),
        settings_file=store.file_name,
    )
    shell.window.show()
    return int(app.exec())
