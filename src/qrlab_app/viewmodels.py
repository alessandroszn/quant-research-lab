"""Qt-free state of the app's screens; widgets only display it and forward user actions."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd

from qrlab.experiments import RunResult, load_config, run_experiment, validate_experiment
from qrlab.experiments.registry import ExperimentKind
from qrlab.experiments.workspace import (
    ConfigEntry,
    RawFileEntry,
    RunEntry,
    config_template,
    create_workspace,
    list_configs,
    list_raw_files,
    list_runs,
)
from qrlab_app.strings import LANGUAGES, tr

__all__ = [
    "MAX_RECENT",
    "AppError",
    "DataViewModel",
    "ExperimentViewModel",
    "HistoryViewModel",
    "RecentWorkspace",
    "ResultView",
    "SettingsStore",
    "SettingsViewModel",
    "TableView",
    "WorkspaceViewModel",
    "load_result",
]

MAX_RECENT = 8
"""Recent workspaces kept in the settings."""


class AppError(Exception):
    """A user action that cannot be done (shown as a message, never a crash).

    It carries a string key and its values, so the screen shows it in the user's language;
    ``str(error)`` is the English text.
    """

    def __init__(self, key: str, **values: object) -> None:
        """Store the key and values; the English text is the exception message."""
        super().__init__(tr(key, "en", **values))
        self.key = key
        self.values = values

    def text(self, language: str) -> str:
        """Return the message in ``language``."""
        return tr(self.key, language, **self.values)


@dataclass(frozen=True)
class TableView:
    """One output table with its sample tag."""

    name: str
    tag: str
    frame: pd.DataFrame


@dataclass(frozen=True)
class ResultView:
    """Everything a finished run wrote, read back from its folder."""

    output_dir: Path
    status: str
    error: str | None
    tables: tuple[TableView, ...]
    scalars: tuple[tuple[str, object, str], ...]  # name, value as recorded, tag
    figures: tuple[Path, ...]
    report: Path | None
    notice: str | None = None


def load_result(output_dir: Path) -> ResultView:
    """Read ``record.json`` and the files it lists (tables, figures, report)."""
    record_path = Path(output_dir) / "record.json"
    if not record_path.is_file():
        raise AppError("error.no_record", folder=output_dir)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    tables, figures, report = [], [], None
    for name, info in sorted(record["outputs"].items()):
        path = Path(output_dir) / name
        if name.endswith(".csv"):
            tables.append(TableView(name[:-4], str(info["tag"]), pd.read_csv(path, index_col=0)))
        elif name.endswith(".png"):
            figures.append(path)
        elif name == "report.html":
            report = path
    scalars = tuple(
        (name, item["value"], str(item["tag"])) for name, item in sorted(record["scalars"].items())
    )
    return ResultView(
        output_dir=Path(output_dir),
        status=str(record["status"]),
        error=record["error"],
        tables=tuple(tables),
        scalars=scalars,
        figures=tuple(figures),
        report=report,
        notice=record.get("notice"),
    )


class WorkspaceViewModel:
    """The open workspace folder (``configs/``, ``data/``, ``results/``)."""

    def __init__(self) -> None:
        """Start with no workspace open."""
        self.root: Path | None = None

    def open(self, root: Path) -> Path:
        """Open an existing folder; its missing standard sub-folders are created."""
        folder = Path(root)
        if not folder.is_dir():
            raise AppError("error.not_folder", folder=folder)
        self.root = create_workspace(folder)
        return self.root

    def create(self, root: Path) -> Path:
        """Create (or complete) a workspace folder and open it."""
        try:
            self.root = create_workspace(Path(root))
        except Exception as exc:  # create_workspace raises QrlabError or OSError
            raise AppError("error.workspace", folder=root, message=str(exc)) from exc
        return self.root

    def require(self) -> Path:
        """Return the open workspace or raise :class:`AppError`."""
        if self.root is None:
            raise AppError("screen.no_workspace")
        return self.root


class ExperimentViewModel:
    """One analysis screen: its configs, the editor text, validation and the run state."""

    def __init__(
        self,
        workspace: WorkspaceViewModel,
        *,
        kinds: Mapping[str, ExperimentKind],
        kind_names: Sequence[str],
    ) -> None:
        """Bind the screen to the kinds it shows."""
        unknown = sorted(set(kind_names) - set(kinds))
        if unknown:
            raise AppError("error.unknown_kinds", kinds=unknown)
        self.workspace = workspace
        self.kinds = kinds
        self.kind_names = tuple(kind_names)
        self.entries: list[ConfigEntry] = []
        self.selected: Path | None = None
        self.text = ""
        self.saved_text = ""
        self.status = "idle"
        self.result: ResultView | None = None
        self.error: str | None = None

    # ---------------------------------------------------------------------- configs
    def refresh(self) -> list[ConfigEntry]:
        """List the workspace configs of this screen's kinds (and unreadable ones)."""
        root = self.workspace.require()
        self.entries = [
            e
            for e in list_configs(root, kinds=self.kinds)
            if e.kind is None or e.kind in self.kind_names
        ]
        return self.entries

    def select(self, path: Path) -> str:
        """Load a config into the editor and its last result, if any."""
        self.selected = Path(path)
        self.text = self.selected.read_text(encoding="utf-8")
        self.saved_text = self.text
        self.error = None
        self.status = "idle"
        self.result = self._existing_result()
        return self.text

    def set_text(self, text: str) -> None:
        """Replace the editor text (not yet saved)."""
        self.text = text

    @property
    def dirty(self) -> bool:
        """Whether the editor text differs from what was last loaded or saved."""
        return self.selected is not None and self.text != self.saved_text

    def save(self) -> Path:
        """Write the editor text to the selected file."""
        path = self._require_selected()
        path.write_text(self.text, encoding="utf-8", newline="\n")
        self.saved_text = self.text
        return path

    def revert(self) -> str:
        """Drop unsaved edits; return the text last loaded or saved."""
        self.text = self.saved_text
        return self.text

    def clear(self) -> None:
        """Forget the selection (another workspace was opened)."""
        self.entries = []
        self.selected = None
        self.text = self.saved_text = ""
        self.status = "idle"
        self.result = None
        self.error = None

    def new_from_template(self, kind_name: str, file_name: str) -> Path:
        """Create ``configs/<file_name>.toml`` from the kind's template and select it."""
        if kind_name not in self.kind_names:
            raise AppError("error.not_on_screen", kind=kind_name)
        path = self._new_path(file_name)
        path.write_text(config_template(self.kinds[kind_name]), encoding="utf-8", newline="\n")
        self.select(path)
        return path

    def duplicate(self, file_name: str) -> Path:
        """Copy the selected config to ``configs/<file_name>.toml`` and select the copy."""
        source = self._require_selected()
        path = self._new_path(file_name)
        path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        self.select(path)
        return path

    # -------------------------------------------------------------------- validate
    def validate(self) -> tuple[bool, str]:
        """Save, then validate with the runner; the message is the runner's own."""
        path = self.save()
        try:
            config, kind, _ = validate_experiment(path, kinds=self.kinds)
        except Exception as exc:  # any config problem is reported verbatim, never raised
            return False, f"{type(exc).__name__}: {exc}"
        return True, f"{config.name} ({kind.name})"

    def output_exists(self) -> bool:
        """Whether running the selected config would replace earlier outputs."""
        path = self._require_selected()
        try:
            return load_config(path).output_dir.exists()
        except Exception:  # an unreadable config has no output folder to replace
            return False

    # ------------------------------------------------------------------------- run
    def start_run(self) -> Callable[[], RunResult]:
        """Validate and return the job for a worker thread; the state becomes running."""
        if self.status == "running":
            raise AppError("screen.busy")
        ok, message = self.validate()
        if not ok:
            raise AppError("screen.invalid", error=message)
        path, kinds = self._require_selected(), self.kinds
        self.status = "running"
        self.error = None
        return lambda: run_experiment(path, kinds=kinds, overwrite=True)

    def finish(self, result: RunResult) -> ResultView:
        """Record a finished run (success or recorded failure) and load its outputs."""
        self.result = load_result(result.output_dir)
        self.status = "done" if result.succeeded else "failed"
        self.error = self.result.error
        return self.result

    def fail(self, message: str) -> None:
        """Record a run that raised before writing a record."""
        self.status = "failed"
        self.error = message

    # --------------------------------------------------------------------- helpers
    def _require_selected(self) -> Path:
        if self.selected is None:
            raise AppError("error.no_selection")
        return self.selected

    def _new_path(self, file_name: str) -> Path:
        name = file_name.strip()
        if not name or any(c in name for c in '/\\:*?"<>|') or name.startswith("."):
            raise AppError("error.bad_name", name=repr(file_name))
        path = self.workspace.require() / "configs" / f"{name}.toml"
        if path.exists():
            raise AppError("error.exists", name=path.name)
        return path

    def _existing_result(self) -> ResultView | None:
        try:
            output_dir = load_config(self._require_selected()).output_dir
            return load_result(output_dir)
        except Exception:  # no readable config or no finished run yet
            return None


class HistoryViewModel:
    """All recorded runs of the workspace, newest first."""

    def __init__(self, workspace: WorkspaceViewModel) -> None:
        """Bind to the workspace."""
        self.workspace = workspace
        self.runs: list[RunEntry] = []

    def refresh(self) -> list[RunEntry]:
        """Read the records again."""
        self.runs = list_runs(self.workspace.require())
        return self.runs


class DataViewModel:
    """Raw-store files of the workspace with provenance and age."""

    def __init__(self, workspace: WorkspaceViewModel, *, now: Callable[[], datetime]) -> None:
        """Bind to the workspace; ``now`` is an explicit clock (timezone-aware)."""
        self.workspace = workspace
        self.now = now
        self.files: list[RawFileEntry] = []

    def refresh(self) -> list[RawFileEntry]:
        """Read the raw store again."""
        self.files = list_raw_files(self.workspace.require(), now=self.now())
        return self.files


# ------------------------------------------------------------------------------ settings
class SettingsStore(Protocol):
    """Where settings live: strings by key (``QSettings`` in the app, a dict in tests)."""

    def get(self, key: str) -> str | None:
        """Return the stored value or ``None``."""

    def set(self, key: str, value: str) -> None:
        """Store a value."""


@dataclass(frozen=True)
class RecentWorkspace:
    """A recently opened workspace; ``exists`` is false when its folder is gone."""

    path: Path
    exists: bool


class SettingsViewModel:
    """Language, recent workspaces and window geometry, kept between sessions.

    Parameters
    ----------
    store
        Where the values are kept.
    system_language
        The system locale's name, such as ``"it_IT"``: until a language is chosen the app is
        in Italian when it starts with ``it``, in English otherwise.
    """

    def __init__(self, store: SettingsStore, *, system_language: str) -> None:
        """Bind to a store."""
        self.store = store
        self.default_language = "it" if system_language.lower().startswith("it") else "en"

    @property
    def language(self) -> str:
        """The chosen language; an unknown stored value falls back to the default."""
        stored = self.store.get("language")
        return stored if stored in LANGUAGES else self.default_language

    def set_language(self, language: str) -> None:
        """Choose the interface language."""
        if language not in LANGUAGES:
            raise AppError("error.language", code=language)
        self.store.set("language", language)

    def recent(self) -> list[RecentWorkspace]:
        """Recent workspaces, most recent first; a stored value that cannot be read is ignored."""
        return [RecentWorkspace(p, p.is_dir()) for p in self._paths()]

    def remember(self, root: Path) -> None:
        """Put ``root`` first, without duplicates, keeping at most :data:`MAX_RECENT`."""
        folder = Path(root).resolve()
        paths = [folder] + [p for p in self._paths() if p.resolve() != folder]
        self._write(paths[:MAX_RECENT])

    def forget(self, root: Path) -> None:
        """Remove ``root`` from the recent workspaces."""
        folder = Path(root).resolve()
        self._write([p for p in self._paths() if p.resolve() != folder])

    def clear_recent(self) -> None:
        """Remove every recent workspace."""
        self._write([])

    @property
    def geometry(self) -> str | None:
        """The saved window geometry (hex), if any."""
        return self.store.get("window_geometry")

    def set_geometry(self, value: str) -> None:
        """Save the window geometry (hex)."""
        self.store.set("window_geometry", value)

    def _paths(self) -> list[Path]:
        raw = self.store.get("recent_workspaces")
        try:
            values = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            return []
        return [Path(v) for v in values]

    def _write(self, paths: list[Path]) -> None:
        self.store.set("recent_workspaces", json.dumps([str(p) for p in paths]))
