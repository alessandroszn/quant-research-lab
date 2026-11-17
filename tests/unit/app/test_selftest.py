"""The app's ``--self-test`` mode (design note 6.2), off-screen.

The self-test runs every config through the queue, each in its own child process (design note
12.2b): the tests that run configs are integration tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from qrlab_app import widgets
from qrlab_app.app import USAGE, main
from qrlab_app.runs import Outcome
from qrlab_app.selftest import MemorySettingsStore, self_test

ROOT = Path(__file__).parents[3]
PROJECTION = ROOT / "configs" / "experiments" / "example_projection.toml"


def _workspace(tmp: Path, *, broken: bool = False) -> Path:
    root = tmp / "ws"
    (root / "configs").mkdir(parents=True)
    text = PROJECTION.read_text(encoding="utf-8").replace("paths = 5000", "paths = 50")
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    text = text[:start] + 'directory = "../results/projection"' + text[end + 1 :]
    (root / "configs" / "projection.toml").write_text(text, encoding="utf-8")
    if broken:
        bad = text.replace("paths = 50", "paths = 5").replace("results/projection", "results/b")
        (root / "configs" / "bad.toml").write_text(bad, encoding="utf-8")
    return root


@pytest.fixture
def no_user_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if the self-test opens the user's settings file."""

    def refuse() -> None:
        raise AssertionError("the self-test touched the user's settings")

    monkeypatch.setattr(widgets.QtSettingsStore, "for_user", refuse)


@pytest.mark.integration
def test_self_test_runs_every_config(
    qapp: QApplication, tmp_path: Path, no_user_settings: None
) -> None:
    root = _workspace(tmp_path)
    lines: list[str] = []
    assert self_test(root, log=lines.append) == 0
    assert (root / "results" / "projection" / "record.json").is_file()
    assert lines[-1] == "self-test: 1 of 1 runs succeeded"
    assert main(["--self-test", str(root)]) == 0  # the same through the entry point


@pytest.mark.integration
def test_self_test_fails_on_an_invalid_config(
    qapp: QApplication, tmp_path: Path, no_user_settings: None
) -> None:
    lines: list[str] = []
    assert self_test(_workspace(tmp_path, broken=True), log=lines.append) == 1
    assert any(line.startswith("self-test: bad.toml: FAILED Not valid:") for line in lines)
    assert lines[-1] == "self-test: 1 of 2 runs succeeded"


def test_self_test_fails_when_nothing_is_tested(
    qapp: QApplication, tmp_path: Path, no_user_settings: None
) -> None:
    lines: list[str] = []
    empty = tmp_path / "empty"
    empty.mkdir()
    assert self_test(empty, log=lines.append) == 1
    assert lines == ["self-test: portfolios: []", "self-test: the workspace has no configs"]
    assert self_test(tmp_path / "missing", log=lines.append) == 1
    assert lines[-1].startswith("self-test: cannot open")


class BrokenRun:
    """A run whose process reports an error."""

    def poll(self) -> Outcome:
        return Outcome(error="RuntimeError: the run broke")

    def cancel(self) -> None:
        raise AssertionError("nothing is cancelled")  # pragma: no cover


def test_self_test_fails_when_a_run_fails(
    qapp: QApplication, tmp_path: Path, no_user_settings: None
) -> None:
    lines: list[str] = []
    assert self_test(_workspace(tmp_path), log=lines.append, starter=lambda c: BrokenRun()) == 1
    assert lines[1] == (
        "self-test: projection.toml: FAILED Failed: Refused before running: "
        "RuntimeError: the run broke"
    )  # lines[0] lists the portfolios


def test_command_line_usage(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from qrlab_app import app

    monkeypatch.setattr(app, "_open_window", lambda: 7)
    assert main([]) == 7  # no arguments: the window opens
    assert main(["--self-test"]) == 2
    assert main(["--other"]) == 2
    assert capsys.readouterr().err.count(USAGE) == 2


def test_memory_settings_store() -> None:
    store = MemorySettingsStore()
    assert store.get("language") is None
    store.set("language", "it")
    assert store.get("language") == "it"
