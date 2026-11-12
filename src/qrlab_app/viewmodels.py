"""Qt-free state of the app's screens; widgets only display it and forward user actions."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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

__all__ = [
    "AppError",
    "DataViewModel",
    "ExperimentViewModel",
    "HistoryViewModel",
    "ResultView",
    "TableView",
    "WorkspaceViewModel",
    "load_result",
]


class AppError(Exception):
    """A user action that cannot be done (shown as a message, never a crash)."""


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
    scalars: tuple[tuple[str, str, str], ...]  # name, value, tag
    figures: tuple[Path, ...]
    report: Path | None


def load_result(output_dir: Path) -> ResultView:
    """Read ``record.json`` and the files it lists (tables, figures, report)."""
    record_path = Path(output_dir) / "record.json"
    if not record_path.is_file():
        raise AppError(f"no record.json in {output_dir}: the run did not finish")
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
        (name, str(item["value"]), str(item["tag"]))
        for name, item in sorted(record["scalars"].items())
    )
    return ResultView(
        output_dir=Path(output_dir),
        status=str(record["status"]),
        error=record["error"],
        tables=tuple(tables),
        scalars=scalars,
        figures=tuple(figures),
        report=report,
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
            raise AppError(f"{folder} is not a folder")
        self.root = create_workspace(folder)
        return self.root

    def create(self, root: Path) -> Path:
        """Create (or complete) a workspace folder and open it."""
        try:
            self.root = create_workspace(Path(root))
        except Exception as exc:  # create_workspace raises QrlabError or OSError
            raise AppError(str(exc)) from exc
        return self.root

    def require(self) -> Path:
        """Return the open workspace or raise :class:`AppError`."""
        if self.root is None:
            raise AppError("no workspace is open")
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
            raise AppError(f"unknown kinds {unknown}")
        self.workspace = workspace
        self.kinds = kinds
        self.kind_names = tuple(kind_names)
        self.entries: list[ConfigEntry] = []
        self.selected: Path | None = None
        self.text = ""
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
        self.error = None
        self.status = "idle"
        self.result = self._existing_result()
        return self.text

    def set_text(self, text: str) -> None:
        """Replace the editor text (not yet saved)."""
        self.text = text

    def save(self) -> Path:
        """Write the editor text to the selected file."""
        path = self._require_selected()
        path.write_text(self.text, encoding="utf-8", newline="\n")
        return path

    def new_from_template(self, kind_name: str, file_name: str) -> Path:
        """Create ``configs/<file_name>.toml`` from the kind's template and select it."""
        if kind_name not in self.kind_names:
            raise AppError(f"{kind_name} is not shown on this screen")
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
            raise AppError("another run is in progress")
        ok, message = self.validate()
        if not ok:
            raise AppError(message)
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
            raise AppError("no config is selected")
        return self.selected

    def _new_path(self, file_name: str) -> Path:
        name = file_name.strip()
        if not name or any(c in name for c in '/\\:*?"<>|') or name.startswith("."):
            raise AppError(f"{file_name!r} is not a valid file name")
        path = self.workspace.require() / "configs" / f"{name}.toml"
        if path.exists():
            raise AppError(f"{path.name} already exists")
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
