"""App view-models without Qt: configs, validation, the run state machine and listings."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qrlab.data.provenance import Provenance
from qrlab.data.store import RawStore
from qrlab.experiments import RunResult
from qrlab.experiments.kinds import KINDS
from qrlab_app.strings import LANGUAGES, STRINGS, tr
from qrlab_app.viewmodels import (
    AppError,
    DataViewModel,
    ExperimentViewModel,
    HistoryViewModel,
    WorkspaceViewModel,
    load_result,
)

ROOT = Path(__file__).parents[3]
PROJECTION = ROOT / "configs" / "experiments" / "example_projection.toml"


def _workspace(tmp: Path) -> WorkspaceViewModel:
    ws = WorkspaceViewModel()
    ws.create(tmp / "ws")
    text = PROJECTION.read_text(encoding="utf-8")
    text = text.replace("paths = 5000", "paths = 50")
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    text = text[:start] + 'directory = "../results/projection"' + text[end + 1 :]
    (tmp / "ws" / "configs" / "projection.toml").write_text(text, encoding="utf-8")
    return ws


def _screen(ws: WorkspaceViewModel) -> ExperimentViewModel:
    return ExperimentViewModel(ws, kinds=KINDS, kind_names=["projection"])


def test_workspace_open_create_and_require(tmp_path: Path) -> None:
    ws = WorkspaceViewModel()
    with pytest.raises(AppError, match="no workspace"):
        ws.require()
    with pytest.raises(AppError, match="not a folder"):
        ws.open(tmp_path / "missing")
    (tmp_path / "plain").mkdir()
    assert ws.open(tmp_path / "plain") == tmp_path / "plain"
    assert (tmp_path / "plain" / "configs").is_dir()
    file = tmp_path / "file.txt"
    file.write_text("x")
    with pytest.raises(AppError, match="is a file"):
        ws.create(file)


def test_configs_are_filtered_by_kind(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    (tmp_path / "ws" / "configs" / "broken.toml").write_text("x = [", encoding="utf-8")
    backtest = (ROOT / "configs" / "experiments" / "example_backtest.toml").read_text("utf-8")
    (tmp_path / "ws" / "configs" / "bt.toml").write_text(backtest, encoding="utf-8")
    entries = _screen(ws).refresh()
    # The backtest config belongs to another screen; the broken one is shown everywhere.
    assert [e.path.name for e in entries] == ["broken.toml", "projection.toml"]
    with pytest.raises(AppError, match="unknown kinds"):
        ExperimentViewModel(ws, kinds=KINDS, kind_names=["nope"])


def test_select_edit_validate(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    screen = _screen(ws)
    with pytest.raises(AppError, match="no config is selected"):
        screen.save()
    path = tmp_path / "ws" / "configs" / "projection.toml"
    text = screen.select(path)
    assert 'kind = "projection"' in text
    assert screen.result is None  # never run
    ok, message = screen.validate()
    assert ok
    assert "(projection)" in message
    screen.set_text(text.replace("paths = 50", "paths = 5"))
    ok, message = screen.validate()
    assert not ok
    assert message.startswith("ValidationError:")
    assert "paths = 5\n" in path.read_text(encoding="utf-8")  # saved before validating


def test_run_state_machine(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    screen = _screen(ws)
    screen.select(tmp_path / "ws" / "configs" / "projection.toml")
    assert not screen.output_exists()
    job = screen.start_run()
    assert screen.status == "running"
    with pytest.raises(AppError, match="another run"):
        screen.start_run()
    result = screen.finish(job())
    assert screen.status == "done"
    assert screen.error is None
    assert {t.name for t in result.tables} >= {"fan_real", "terminal"}
    assert all(t.tag == "descriptive" for t in result.tables)
    assert result.report is None
    assert result.figures[0].suffix == ".png"
    assert [name for name, _, _ in result.scalars] == [
        "p_depleted",
        "p_goal",
        "p_goal_se",
        "terminal_mean_real",
    ]
    assert screen.output_exists()
    # Selecting the config again loads its last result.
    screen.select(tmp_path / "ws" / "configs" / "projection.toml")
    assert screen.result is not None
    assert screen.result.status == "success"
    screen.fail("ValueError: boom")
    assert screen.status == "failed"
    assert screen.error == "ValueError: boom"


def test_invalid_config_does_not_start(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    screen = _screen(ws)
    screen.select(tmp_path / "ws" / "configs" / "projection.toml")
    screen.set_text("kind = 1")
    with pytest.raises(AppError, match="ValidationError"):
        screen.start_run()
    assert screen.status == "idle"
    assert not screen.output_exists()


def test_failed_run_is_recorded(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    screen = _screen(ws)
    screen.select(tmp_path / "ws" / "configs" / "projection.toml")
    # A run that fails inside the kind still writes a record with status "failure".
    folder = tmp_path / "ws" / "results" / "failed"
    folder.mkdir(parents=True)
    record = {"status": "failure", "error": "ValidationError: x", "outputs": {}, "scalars": {}}
    (folder / "record.json").write_text(json.dumps(record), encoding="utf-8")
    screen.status = "running"
    view = screen.finish(RunResult(folder, record))
    assert screen.status == "failed"
    assert screen.error == "ValidationError: x"
    assert view.tables == ()


def test_new_and_duplicate(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    screen = _screen(ws)
    created = screen.new_from_template("projection", "mine")
    assert created.name == "mine.toml"
    assert screen.selected == created
    assert "FILL-IN" in screen.text
    copy = screen.duplicate("mine-copy")
    assert copy.read_text(encoding="utf-8") == created.read_text(encoding="utf-8")
    for bad in ("", "a/b", ".hidden"):
        with pytest.raises(AppError, match="not a valid file name"):
            screen.new_from_template("projection", bad)
    with pytest.raises(AppError, match="already exists"):
        screen.new_from_template("projection", "mine")
    with pytest.raises(AppError, match="not shown on this screen"):
        screen.new_from_template("backtest", "x")


def test_load_result_needs_a_record(tmp_path: Path) -> None:
    with pytest.raises(AppError, match="did not finish"):
        load_result(tmp_path)


def test_history_and_data(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    screen = _screen(ws)
    screen.select(tmp_path / "ws" / "configs" / "projection.toml")
    screen.finish(screen.start_run()())
    runs = HistoryViewModel(ws).refresh()
    assert [r.kind for r in runs] == ["projection"]
    content = b"raw"
    RawStore(tmp_path / "ws" / "data").put(
        content,
        Provenance(
            source="ecb",
            dataset="fx",
            url="https://example.org/fx.zip",
            retrieved_at=datetime(2026, 11, 10, tzinfo=UTC),
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            terms="t",
        ),
    )
    data = DataViewModel(ws, now=lambda: datetime(2026, 11, 12, tzinfo=UTC))
    files = data.refresh()
    assert [(f.dataset, f.age_days) for f in files] == [("fx", 2)]


def test_strings() -> None:
    assert tuple(STRINGS) == LANGUAGES
    assert tr("home.current", "en", path="C:/x") == "Workspace: C:/x"
    with pytest.raises(KeyError, match="unsupported language"):
        tr("app.title", "fr")


def test_load_result_reads_report_and_ignores_other_files(tmp_path: Path) -> None:
    (tmp_path / "report.html").write_text("<html></html>", encoding="utf-8")
    record = {
        "status": "success",
        "error": None,
        "outputs": {
            "report.html": {"tag": "descriptive"},
            "notes.txt": {"tag": "descriptive"},
        },
        "scalars": {},
    }
    (tmp_path / "record.json").write_text(json.dumps(record), encoding="utf-8")
    view = load_result(tmp_path)
    assert view.report == tmp_path / "report.html"
    assert view.tables == ()
    assert view.figures == ()
