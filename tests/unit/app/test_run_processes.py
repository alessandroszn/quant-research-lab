"""Runs in real child processes (design note 12.2b): the same outputs, a real cancel."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from qrlab.experiments import RunResult, run_experiment, staging_dir
from qrlab.experiments.kinds import KINDS
from qrlab_app.runs import CANCELLED, RUNNING, Outcome, ProcessHandle, ProcessStarter, RunQueue
from run_helpers import SLOW, slow_config

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parents[3]
TIMEOUT = 180.0


def _wait(handle: ProcessHandle) -> Outcome:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        outcome = handle.poll()
        if outcome is not None:
            return outcome
        time.sleep(0.1)
    raise AssertionError("the child process did not finish")  # pragma: no cover


def _projection(folder: Path, out: str) -> Path:
    text = (ROOT / "configs/experiments/example_projection.toml").read_text(encoding="utf-8")
    text = text.replace("paths = 5000", "paths = 50")
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{out}.toml"
    path.write_text(text[:start] + f'directory = "{out}"' + text[end + 1 :], encoding="utf-8")
    return path


def test_a_run_in_a_child_process_writes_what_it_writes_here(tmp_path: Path) -> None:
    here = run_experiment(_projection(tmp_path, "here"), kinds=KINDS, overwrite=False)
    outcome = _wait(ProcessStarter()(_projection(tmp_path, "child")))
    assert outcome.error is None
    assert isinstance(outcome.result, RunResult)
    child = outcome.result
    assert child.succeeded
    assert child.output_dir == tmp_path / "child"
    files = sorted(p.name for p in here.output_dir.iterdir() if p.name != "record.json")
    assert files == sorted(p.name for p in child.output_dir.iterdir() if p.name != "record.json")
    for name in files:
        assert (here.output_dir / name).read_bytes() == (child.output_dir / name).read_bytes()
    assert child.record["scalars"] == here.record["scalars"]
    assert child.record["outputs"] == here.record["outputs"]


def test_a_refused_config_and_a_process_that_dies(tmp_path: Path) -> None:
    refused = _wait(ProcessStarter()(tmp_path / "missing.toml"))
    assert refused.result is None
    assert refused.error is not None
    assert refused.error.startswith("ValidationError: config file")
    handle = ProcessStarter("run_helpers")(slow_config(tmp_path, 60))
    handle.process.kill()  # ended from outside, without a word
    died = _wait(handle)
    assert died.result is None
    assert died.exit_code is not None
    assert died.exit_code != 0


def test_cancelling_a_running_child_keeps_the_earlier_results(tmp_path: Path) -> None:
    config = slow_config(tmp_path, 0)
    earlier = run_experiment(config, kinds={"slow": SLOW}, overwrite=False)
    before = {p.name: p.read_bytes() for p in earlier.output_dir.iterdir()}
    config.write_text(config.read_text(encoding="utf-8").replace("= 0", "= 60"), "utf-8")
    queue = RunQueue(ProcessStarter("run_helpers"))
    entry = queue.add(config)
    queue.step()
    assert entry.state == RUNNING
    deadline = time.monotonic() + TIMEOUT
    while not staging_dir(entry.output_dir).exists():  # the child is inside the kind's run
        assert time.monotonic() < deadline
        assert queue.step() == []
        time.sleep(0.1)
    started = time.monotonic()
    queue.cancel(entry)
    assert time.monotonic() - started < 10  # ended at once, not after the 60 s
    assert entry.state == CANCELLED
    assert entry.note_text("en") == "Cancelled; the earlier results are unchanged."
    assert not staging_dir(entry.output_dir).exists()
    assert {p.name: p.read_bytes() for p in earlier.output_dir.iterdir()} == before
    ledger = (tmp_path / "out" / "trials.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 1  # the cancelled run is not a trial
