"""The main window (a navigation list and one page per screen) and the shell that owns it."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from qrlab.experiments.registry import ExperimentKind
from qrlab_app.portfolio import PortfolioViewModel
from qrlab_app.portfolio_screen import PortfolioScreen
from qrlab_app.runs import QueueEntry, RunQueue, RunStarter
from qrlab_app.screens import (
    DataScreen,
    ExperimentScreen,
    HistoryScreen,
    HomeScreen,
    QueueScreen,
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

__all__ = ["ANALYSIS_SCREENS", "ICON", "QUEUE_TICK_MS", "AppShell", "MainWindow"]

ICON = Path(__file__).parent / "resources" / "qrlab.png"
"""The app's icon (design note 12.4), drawn by ``packaging/make_icon.py``."""

QUEUE_TICK_MS = 200
"""How often the window checks the running run and starts the next one."""

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
    starter
        Starts each run (in its own process in the app, design note 12.2b).
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
        starter: RunStarter,
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
        self.queue = RunQueue(starter)
        self._shown_seconds = -1
        self.home = HomeScreen(
            self.workspace,
            settings,
            dialogs,
            language,
            can_leave=lambda: self.confirm_leave(None),
            on_change=self.workspace_opened,
        )
        self.portfolios = PortfolioScreen(
            PortfolioViewModel(self.workspace, kinds=kinds, now=now),
            dialogs,
            language,
            on_report=self.open_report,
        )
        self.analysis = [
            ExperimentScreen(
                ExperimentViewModel(self.workspace, kinds=kinds, kind_names=names),
                dialogs,
                language,
                self.queue,
                self.tick,
            )
            for _, names in ANALYSIS_SCREENS
        ]
        self.data = DataScreen(DataViewModel(self.workspace, now=now), dialogs, language)
        self.queue_screen = QueueScreen(self.queue, dialogs, language, self.tick)
        self.history = HistoryScreen(HistoryViewModel(self.workspace), dialogs, language)
        self.settings_screen = SettingsScreen(
            settings,
            language,
            settings_file=settings_file,
            on_language=self.change_language,
            on_recent_change=self.home.refresh_recent,
        )
        pages: list[tuple[str, QWidget]] = [
            ("nav.home", self.home),
            ("nav.portfolios", self.portfolios),
        ]
        pages += [
            (key, screen) for (key, _), screen in zip(ANALYSIS_SCREENS, self.analysis, strict=True)
        ]
        pages += [
            ("nav.data", self.data),
            ("nav.queue", self.queue_screen),
            ("nav.history", self.history),
            ("nav.settings", self.settings_screen),
        ]
        self._refreshers: list[Callable[[], None]] = [  # one per page, in navigation order
            self.home.refresh_recent,
            self.portfolios.refresh,
            *(screen.refresh for screen in self.analysis),
            self.data.refresh,
            self.queue_screen.refresh,
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
        self.setWindowIcon(QIcon(str(ICON)))
        self.navigation.setCurrentRow(0)
        self.resize(1280, 800)
        if settings.geometry:
            self.restoreGeometry(QByteArray.fromHex(settings.geometry.encode("ascii")))
        self._title()
        self.timer = QTimer(self)
        self.timer.setInterval(QUEUE_TICK_MS)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def screen_for(self, kind: str) -> ExperimentScreen:
        """Return the analysis screen that shows ``kind``."""
        for screen in self.analysis:
            if kind in screen.model.kind_names:
                return screen
        raise KeyError(kind)

    def open_report(self, path: Path) -> None:
        """Show a report config created on the Portfolio screen, on the report's screen."""
        screen = self.screen_for("portfolio_report")
        screen.open_config(path)
        self.navigation.setCurrentRow(self.stack.indexOf(screen))

    def tick(self, changed: Sequence[QueueEntry] = ()) -> None:
        """Collect the running run's outcome, start the next one and show what changed.

        Called by the timer, and by a screen with the entries it added or cancelled.
        """
        changed = [*changed, *self.queue.step()]
        for screen in self.analysis:
            screen.queue_changed(changed)
        running = next((e for e in self.queue.active() if e.started is not None), None)
        seconds = -1 if running is None else self.queue.elapsed(running)
        if changed or seconds != self._shown_seconds:
            self._shown_seconds = seconds
            self.queue_screen.refresh()
        if self.workspace.root is not None and any(e.result is not None for e in changed):
            self.history.refresh()

    def confirm_leave(self, busy_key: str | None) -> bool:
        """Settle runs and unsaved edits before leaving; ``False`` means stay.

        With runs waiting or running, a ``busy_key`` refuses and says why; without one the
        user is asked whether to cancel them, and they are cancelled only once every unsaved
        edit is settled too.
        """
        active = self.queue.active()
        if active and busy_key is not None:
            self.dialogs.inform(tr(busy_key, self.language))
            return False
        if active and not self.dialogs.confirm(tr("queue.leave", self.language, count=len(active))):
            return False
        if not self.portfolios.confirm_discard() or not all(
            screen.confirm_discard() for screen in self.analysis
        ):
            return False
        if active:
            self.queue.cancel_all()
            self.tick(active)
        return True

    def workspace_opened(self) -> None:
        """Reset every screen to the workspace just opened."""
        for screen in self.analysis:
            screen.reset()
        self.portfolios.reset()
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
        """Ask about runs and unsaved edits before closing; remember the geometry."""
        if not self.confirm_leave(None):
            event.ignore()
            return
        self.timer.stop()
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
        if isinstance(page, QueueScreen):
            page.refresh()


class AppShell:
    """Owns the current main window and rebuilds it when the language changes.

    The workspace survives the rebuild, so the new window shows the same folder on the same
    screen; unsaved edits were settled and no run was waiting or running (``change_language``).
    """

    def __init__(
        self,
        *,
        kinds: Mapping[str, ExperimentKind],
        dialogs: Dialogs,
        settings: SettingsViewModel,
        now: Callable[[], datetime],
        starter: RunStarter,
        settings_file: str,
    ) -> None:
        """Build the first window (not shown yet)."""
        self._kinds = kinds
        self._dialogs = dialogs
        self._settings = settings
        self._now = now
        self._starter = starter
        self._settings_file = settings_file
        self.workspace = WorkspaceViewModel()
        self.window = self._build()

    def _build(self) -> MainWindow:
        return MainWindow(
            kinds=self._kinds,
            dialogs=self._dialogs,
            settings=self._settings,
            now=self._now,
            starter=self._starter,
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
