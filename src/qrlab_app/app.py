"""Start the desktop app (``qrlab-app``), or run its self-test (``--self-test WORKSPACE``)."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QLocale
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from qrlab.experiments.kinds import KINDS
from qrlab_app.main_window import ICON, AppShell
from qrlab_app.runs import ProcessStarter
from qrlab_app.selftest import self_test
from qrlab_app.viewmodels import SettingsViewModel
from qrlab_app.widgets import QtSettingsStore, default_dialogs

__all__ = ["USAGE", "main"]

USAGE = "usage: qrlab-app [--self-test WORKSPACE]"


def main(argv: Sequence[str] | None = None) -> int:
    """Open the app, or run the self-test on a workspace; return the exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--self-test":
        if len(args) != 2:
            print(USAGE, file=sys.stderr)
            return 2
        return self_test(Path(args[1]))
    if args:
        print(USAGE, file=sys.stderr)
        return 2
    return _open_window()


def _open_window() -> int:  # pragma: no cover - starts the event loop; the smoke test builds it
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ICON)))  # the taskbar's icon
    store = QtSettingsStore.for_user()
    shell = AppShell(
        kinds=KINDS,
        dialogs=default_dialogs(None),
        settings=SettingsViewModel(store, system_language=QLocale.system().name()),
        now=lambda: datetime.now(UTC),
        starter=ProcessStarter(),
        settings_file=store.file_name,
    )
    shell.window.show()
    return int(app.exec())
