"""Start the desktop app (``qrlab-app``)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from qrlab.experiments.kinds import KINDS
from qrlab_app.main_window import MainWindow
from qrlab_app.widgets import default_dialogs

__all__ = ["main"]


def main() -> int:  # pragma: no cover - starts the event loop; the smoke test builds the window
    """Open the main window and run until it is closed."""
    app = QApplication(sys.argv)
    window = MainWindow(
        kinds=KINDS,
        dialogs=default_dialogs(None),  # type: ignore[arg-type]
        language="en",
        now=lambda: datetime.now(UTC),
        pool=QThreadPool.globalInstance(),
    )
    window.show()
    return int(app.exec())
