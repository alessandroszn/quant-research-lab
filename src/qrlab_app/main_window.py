"""The main window: a navigation list on the left and one page per screen."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from qrlab.experiments.registry import ExperimentKind
from qrlab_app.screens import DataScreen, ExperimentScreen, HistoryScreen, HomeScreen
from qrlab_app.strings import tr
from qrlab_app.viewmodels import (
    DataViewModel,
    ExperimentViewModel,
    HistoryViewModel,
    WorkspaceViewModel,
)
from qrlab_app.widgets import Dialogs

__all__ = ["ANALYSIS_SCREENS", "MainWindow"]

ANALYSIS_SCREENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nav.portfolio", ("portfolio_report",)),
    ("nav.risk", ("risk_report",)),
    ("nav.scenarios", ("scenario_analysis",)),
    ("nav.projections", ("projection",)),
    ("nav.optimiser", ("optimisation",)),
    (
        "nav.backtests",
        (
            "backtest",
            "study_volatility_managed",
            "study_one_over_n",
            "study_factor_zoo",
            "study_rebalancing",
        ),
    ),
)
"""Navigation key -> experiment kinds shown on that screen."""


class MainWindow(QMainWindow):
    """Navigation plus the stacked screens; every screen shares one workspace."""

    def __init__(
        self,
        *,
        kinds: Mapping[str, ExperimentKind],
        dialogs: Dialogs,
        language: str,
        now: Callable[[], datetime],
        pool: QThreadPool,
    ) -> None:
        """Build every screen; nothing is loaded until a workspace is opened."""
        super().__init__()
        self.setWindowTitle(tr("app.title", language))
        self.workspace = WorkspaceViewModel()
        self.home = HomeScreen(self.workspace, dialogs, language, self.refresh_all)
        self.analysis = [
            ExperimentScreen(
                ExperimentViewModel(self.workspace, kinds=kinds, kind_names=names),
                dialogs,
                language,
                pool,
            )
            for _, names in ANALYSIS_SCREENS
        ]
        self.data = DataScreen(DataViewModel(self.workspace, now=now), language)
        self.history = HistoryScreen(HistoryViewModel(self.workspace), dialogs, language)
        pages: list[tuple[str, QWidget]] = [("nav.home", self.home)]
        pages += [
            (key, screen) for (key, _), screen in zip(ANALYSIS_SCREENS, self.analysis, strict=True)
        ]
        pages += [("nav.data", self.data), ("nav.history", self.history)]
        self.navigation = QListWidget()
        self.stack = QStackedWidget()
        for key, page in pages:
            self.navigation.addItem(tr(key, language))
            self.stack.addWidget(page)
        self.navigation.currentRowChanged.connect(self._show)
        self.navigation.setFixedWidth(190)
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack)
        self.setCentralWidget(central)
        self.navigation.setCurrentRow(0)
        self.resize(1280, 800)

    def screen_for(self, kind: str) -> ExperimentScreen:
        """Return the analysis screen that shows ``kind``."""
        for screen in self.analysis:
            if kind in screen.model.kind_names:
                return screen
        raise KeyError(kind)

    def refresh_all(self) -> None:
        """Reload every screen after a workspace is opened."""
        for screen in self.analysis:
            screen.refresh()
        self.data.refresh()
        self.history.refresh()

    def _show(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        page = self.stack.currentWidget()
        if self.workspace.root is not None and isinstance(page, (DataScreen, HistoryScreen)):
            page.refresh()
