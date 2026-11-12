"""Qt runs off-screen in tests (no display needed, also in CI)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the one QApplication of the test session."""
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else QApplication([])
