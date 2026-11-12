"""The main window (a navigation list and one page per screen) and the shell that owns it."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

from PySide6.QtCore import QByteArray, QThreadPool
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from qrlab.experiments.registry import ExperimentKind
from qrlab_app.screens import (
    DataScreen,
    ExperimentScreen,
    HistoryScreen,
    HomeScreen,
    SettingsScreen,
)
from qrlab_app.strings import tr
from qrlab_app.viewmodels import (
    DataViewModel,
    ExperimentViewModel,
    HistoryViewModel,
    SettingsViewModel,
    WorkspaceViewModel,
)
from qrlab_app.widgets import Dialogs

__all__ = ["ANALYSIS_SCREENS", "AppShell", "MainWindow"]

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
    """Navigation plus the stacked screens, in one language; every screen shares one workspace.

    Parameters
    ----------
    kinds
        The experiment kinds (``qrlab.experiments.kinds.KINDS``).
    dialogs
        Everything that asks the user something.
    settings
        Language, recent workspaces and window geometry.
    now
        Clock for the age of raw files (timezone-aware).
    pool
        Thread pool for runs.
    workspace
        The workspace shared with an earlier window (language change); a new one by default.
    settings_file
        Where the settings are saved, shown on the Settings screen.
    on_language
        Called with a new language after the window agreed to leave; it rebuilds the window.
    """

    def __init__(
        self,
        *,
        kinds: Mapping[str, ExperimentKind],
        dialogs: Dialogs,
        settings: SettingsViewModel,
        now: Callable[[], datetime],
        pool: QThreadPool,
        workspace: WorkspaceViewModel | None = None,
        settings_file: str = "",
        on_language: Callable[[str], None] | None = None,
    ) -> None:
        """Build every screen; nothing is loaded until a workspace is opened."""
        super().__init__()
        self.language = language = settings.language
        self.dialogs = dialogs
        self.settings = settings
        self.on_language = on_language
        self.workspace = workspace if workspace is not None else WorkspaceViewModel()
        self.home = HomeScreen(
            self.workspace,
            settings,
            dialogs,
            language,
            can_leave=lambda: self.confirm_leave("screen.busy"),
            on_change=self.workspace_opened,
        )
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
        self.settings_screen = SettingsScreen(
            settings,
            language,
            settings_file=settings_file,
            on_language=self.change_language,
            on_recent_change=self.home.refresh_recent,
        )
        pages: list[tuple[str, QWidget]] = [("nav.home", self.home)]
        pages += [
            (key, screen) for (key, _), screen in zip(ANALYSIS_SCREENS, self.analysis, strict=True)
        ]
        pages += [
            ("nav.data", self.data),
            ("nav.history", self.history),
            ("nav.settings", self.settings_screen),
        ]
        self._refreshers: list[Callable[[], None]] = [  # one per page, in navigation order
            self.home.refresh_recent,
            *(screen.refresh for screen in self.analysis),
            self.data.refresh,
            self.history.refresh,
            self.settings_screen.refresh,
        ]
        self.navigation = QListWidget()
        self.stack = QStackedWidget()
        for key, page in pages:
            self.navigation.addItem(tr(key, language))
            self.stack.addWidget(page)
        self.navigation.currentRowChanged.connect(self._show)
        self.navigation.setFixedWidth(190)
        self.refresh_shortcut = QShortcut(QKeySequence.StandardKey.Refresh, self)
        self.refresh_shortcut.activated.connect(self.refresh_current)
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack)
        self.setCentralWidget(central)
        self.navigation.setCurrentRow(0)
        self.resize(1280, 800)
        if settings.geometry:
            self.restoreGeometry(QByteArray.fromHex(settings.geometry.encode("ascii")))
        self._title()

    def screen_for(self, kind: str) -> ExperimentScreen:
        """Return the analysis screen that shows ``kind``."""
        for screen in self.analysis:
            if kind in screen.model.kind_names:
                return screen
        raise KeyError(kind)

    def busy(self) -> bool:
        """Whether a run is in progress on any screen."""
        return any(screen.model.status == "running" for screen in self.analysis)

    def confirm_leave(self, busy_key: str) -> bool:
        """Refuse during a run (telling the user why); otherwise settle every unsaved edit."""
        if self.busy():
            self.dialogs.inform(tr(busy_key, self.language))
            return False
        return all(screen.confirm_discard() for screen in self.analysis)

    def workspace_opened(self) -> None:
        """Reset every screen to the workspace just opened."""
        for screen in self.analysis:
            screen.reset()
        self.home.show_workspace()
        self.data.refresh()
        self.history.refresh()
        self.settings_screen.refresh()
        self._title()

    def refresh_current(self) -> None:
        """Reload the screen on show (F5)."""
        self._refreshers[self.stack.currentIndex()]()

    def change_language(self, language: str) -> bool:
        """Apply a new language by rebuilding the window; ``False`` when it was refused."""
        if not self.confirm_leave("settings.busy"):
            return False
        self.settings.set_language(language)
        if self.on_language is not None:
            self.on_language(language)
        return True

    def save_geometry(self) -> None:
        """Remember the window's size and position."""
        self.settings.set_geometry(bytes(self.saveGeometry().toHex().data()).decode("ascii"))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Refuse to close during a run; ask about unsaved edits; remember the geometry."""
        if not self.confirm_leave("close.busy"):
            event.ignore()
            return
        self.save_geometry()
        event.accept()

    def _title(self) -> None:
        root = self.workspace.root
        self.setWindowTitle(
            tr("app.title", self.language)
            if root is None
            else tr("app.title_workspace", self.language, name=root.name)
        )

    def _show(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        page = self.stack.currentWidget()
        if self.workspace.root is not None and isinstance(page, (DataScreen, HistoryScreen)):
            page.refresh()


class AppShell:
    """Owns the current main window and rebuilds it when the language changes.

    The workspace survives the rebuild, so the new window shows the same folder on the same
    screen; unsaved edits were settled and no run was in progress (``change_language``).
    """

    def __init__(
        self,
        *,
        kinds: Mapping[str, ExperimentKind],
        dialogs: Dialogs,
        settings: SettingsViewModel,
        now: Callable[[], datetime],
        pool: QThreadPool,
        settings_file: str,
    ) -> None:
        """Build the first window (not shown yet)."""
        self._kinds = kinds
        self._dialogs = dialogs
        self._settings = settings
        self._now = now
        self._pool = pool
        self._settings_file = settings_file
        self.workspace = WorkspaceViewModel()
        self.window = self._build()

    def _build(self) -> MainWindow:
        return MainWindow(
            kinds=self._kinds,
            dialogs=self._dialogs,
            settings=self._settings,
            now=self._now,
            pool=self._pool,
            workspace=self.workspace,
            settings_file=self._settings_file,
            on_language=self.rebuild,
        )

    def rebuild(self, language: str) -> None:
        """Replace the window by one in ``language`` (already saved in the settings)."""
        old = self.window
        row = old.navigation.currentRow()
        old.save_geometry()
        new = self._build()
        if self.workspace.root is not None:
            new.workspace_opened()
        new.navigation.setCurrentRow(row)
        self.window = new
        if old.isVisible():
            new.show()
        old.close()
        old.deleteLater()
