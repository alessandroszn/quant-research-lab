"""The run queue without Qt and without processes (design note 12.2b): a scripted starter."""

from __future__ import annotations

from pathlib import Path

import pytest

from qrlab.experiments import RunResult, staging_dir
from qrlab_app.runs import (
    CANCELLED,
    DONE,
    FAILED,
    RUNNING,
    WAITING,
    Outcome,
    RunQueue,
    _child,
    _receive,
    end_process,
)
from qrlab_app.viewmodels import AppError
from run_helpers import KINDS, slow_config


class FakeHandle:
    """A run whose outcome the test decides; ``early`` is how it ended before a cancel."""

    def __init__(self, config: Path) -> None:
        self.config = config
        self.outcome: Outcome | None = None
        self.early: Outcome | None = None
        self.cancelled = False

    def poll(self) -> Outcome | None:
        return self.outcome

    def cancel(self) -> None:
        self.cancelled = True
        self.outcome = self.early or Outcome(exit_code=-15)


class FakeStarter:
    def __init__(self) -> None:
        self.handles: dict[str, FakeHandle] = {}
        self.refuse: set[str] = set()

    def __call__(self, config: Path) -> FakeHandle:
        if config.name in self.refuse:
            raise OSError("no more processes")
        self.handles[config.name] = handle = FakeHandle(config)
        return handle


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _success(entry_dir: Path) -> Outcome:
    return Outcome(result=RunResult(entry_dir, {"status": "success", "error": None}))


def _failure(entry_dir: Path) -> Outcome:
    return Outcome(result=RunResult(entry_dir, {"status": "failure", "error": "RuntimeError: x"}))


@pytest.fixture
def setup(tmp_path: Path) -> tuple[RunQueue, FakeStarter, Clock]:
    starter, clock = FakeStarter(), Clock()
    return RunQueue(starter, clock=clock), starter, clock


def test_one_at_a_time_in_order(tmp_path: Path, setup: tuple[RunQueue, FakeStarter, Clock]) -> None:
    queue, starter, clock = setup
    a = queue.add(slow_config(tmp_path, 0, name="a"))
    b = queue.add(slow_config(tmp_path, 0, name="b"))
    assert (a.number, a.name, a.kind, a.state) == (1, "a", "slow", WAITING)
    assert a.output_dir == tmp_path / "out" / "a"
    assert queue.position(a) == 1
    assert queue.position(b) == 2
    assert queue.elapsed(a) == 0  # not started
    assert queue.step() == [a]
    assert (a.state, b.state) == (RUNNING, WAITING)
    assert list(starter.handles) == ["a.toml"]
    assert queue.active() == [a, b]
    clock.now += 7.6
    assert queue.elapsed(a) == 7
    assert queue.step() == []  # still running
    starter.handles["a.toml"].outcome = _success(a.output_dir)
    clock.now += 1
    assert queue.step() == [a, b]
    assert (a.state, b.state) == (DONE, RUNNING)
    assert a.note is None
    assert a.note_text("en") == ""
    assert a.result is not None
    clock.now += 100
    assert queue.elapsed(a) == 8  # fixed once finished
    assert queue.position(a) == 0
    assert queue.latest(a.config) is a
    assert queue.latest(tmp_path / "nope.toml") is None
    starter.handles["b.toml"].outcome = _failure(b.output_dir)
    assert queue.step() == [b]
    assert b.state == FAILED
    assert b.note_text("en") == "The run failed: RuntimeError: x"
    assert b.note_text("it") == "L'esecuzione non è riuscita: RuntimeError: x"
    assert queue.step() == []
    queue.clear_finished()
    assert queue.entries == []


def test_what_cannot_be_queued(tmp_path: Path, setup: tuple[RunQueue, FakeStarter, Clock]) -> None:
    queue, starter, _ = setup
    config = slow_config(tmp_path, 0, name="a")
    first = queue.add(config)
    with pytest.raises(AppError, match=r"a.toml is already in line and writes the same output"):
        queue.add(config)
    queue.step()
    starter.handles["a.toml"].outcome = _success(first.output_dir)
    queue.step()
    assert queue.add(config).number == 2  # the first one is done: the same folder is free
    with pytest.raises(AppError, match=r"cannot be queued: config file .* does not exist"):
        queue.add(tmp_path / "missing.toml")


def test_a_config_changed_or_removed_after_queuing_is_not_run(
    tmp_path: Path, setup: tuple[RunQueue, FakeStarter, Clock]
) -> None:
    queue, starter, _ = setup
    a = queue.add(slow_config(tmp_path, 0, name="a"))
    b = queue.add(slow_config(tmp_path, 0, name="b"))
    c = queue.add(slow_config(tmp_path, 0, name="c"))
    d = queue.add(slow_config(tmp_path, 0, name="d"))
    b.config.write_text(b.config.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    c.config.unlink()
    assert queue.step() == [a]
    starter.handles["a.toml"].outcome = _success(a.output_dir)
    assert queue.step() == [a, b, c, d]
    assert (b.state, c.state, d.state) == (FAILED, FAILED, RUNNING)
    assert b.note_text("en") == "Not run: the config changed after it was queued."
    assert c.note == b.note


def test_a_run_that_cannot_start(
    tmp_path: Path, setup: tuple[RunQueue, FakeStarter, Clock]
) -> None:
    queue, starter, _ = setup
    a = queue.add(slow_config(tmp_path, 0, name="a"))
    b = queue.add(slow_config(tmp_path, 0, name="b"))
    starter.refuse.add("a.toml")
    assert queue.step() == [a, b]
    assert a.state == FAILED
    assert a.note_text("en") == "Not run: its process could not start (no more processes)."
    assert b.state == RUNNING


def test_refused_and_dead_runs_leave_no_staging_folder(
    tmp_path: Path, setup: tuple[RunQueue, FakeStarter, Clock]
) -> None:
    queue, starter, _ = setup
    a = queue.add(slow_config(tmp_path, 0, name="a"))
    b = queue.add(slow_config(tmp_path, 0, name="b"))
    queue.step()
    staging_dir(a.output_dir).mkdir(parents=True)
    starter.handles["a.toml"].outcome = Outcome(error="ValidationError: input x does not exist")
    queue.step()
    assert a.state == FAILED
    assert a.note_text("en") == "Refused before running: ValidationError: input x does not exist"
    assert not staging_dir(a.output_dir).exists()
    staging_dir(b.output_dir).mkdir(parents=True)
    starter.handles["b.toml"].outcome = Outcome(exit_code=3)
    queue.step()
    assert b.note_text("en") == "The run's process ended unexpectedly (exit code 3)."
    assert not staging_dir(b.output_dir).exists()


def test_cancelling(tmp_path: Path, setup: tuple[RunQueue, FakeStarter, Clock]) -> None:
    queue, starter, _ = setup
    a = queue.add(slow_config(tmp_path, 0, name="a"))
    b = queue.add(slow_config(tmp_path, 0, name="b"))
    c = queue.add(slow_config(tmp_path, 0, name="c"))
    queue.step()
    queue.cancel(b)  # waiting: it leaves the line
    assert b.state == CANCELLED
    assert b.note_text("en") == "Cancelled before it started."
    assert "b.toml" not in starter.handles
    staging_dir(a.output_dir).mkdir(parents=True)  # the run was writing
    queue.cancel(a)
    assert starter.handles["a.toml"].cancelled
    assert a.state == CANCELLED
    assert a.note_text("en") == "Cancelled; there were no earlier results."
    assert not staging_dir(a.output_dir).exists()
    queue.cancel(a)  # finished: nothing happens
    assert a.state == CANCELLED
    assert queue.step() == [c]
    c.output_dir.mkdir(parents=True)
    (c.output_dir / "record.json").write_text("{}", encoding="utf-8")  # an earlier run
    queue.cancel(c)
    assert c.note_text("it") == "Annullata; i risultati precedenti sono invariati."


def test_a_run_that_ended_just_before_the_cancel_keeps_its_outcome(
    tmp_path: Path, setup: tuple[RunQueue, FakeStarter, Clock]
) -> None:
    queue, starter, _ = setup
    a = queue.add(slow_config(tmp_path, 0, name="a"))
    queue.step()
    starter.handles["a.toml"].early = _success(a.output_dir)
    queue.cancel(a)
    assert a.state == DONE
    assert a.note_text("en") == "It finished before it could be cancelled."
    b = queue.add(slow_config(tmp_path, 0, name="b"))
    queue.step()
    starter.handles["b.toml"].early = _failure(b.output_dir)
    queue.cancel(b)
    assert b.state == FAILED
    assert b.note_text("en") == "The run failed: RuntimeError: x"


def test_cancel_all_starts_nothing(
    tmp_path: Path, setup: tuple[RunQueue, FakeStarter, Clock]
) -> None:
    queue, starter, _ = setup
    entries = [queue.add(slow_config(tmp_path, 0, name=n)) for n in ("a", "b", "c")]
    queue.step()
    queue.cancel_all()
    assert [e.state for e in entries] == [CANCELLED] * 3
    assert list(starter.handles) == ["a.toml"]
    assert queue.step() == []
    assert queue.active() == []


# ------------------------------------------------------------------------------ the child's parts
class Sent:
    def __init__(self) -> None:
        self.messages: list[tuple[object, ...]] = []
        self.closed = False

    def send(self, message: tuple[object, ...]) -> None:
        self.messages.append(message)

    def close(self) -> None:
        self.closed = True


def test_the_child_sends_the_record_or_the_refusal(tmp_path: Path) -> None:
    sent = Sent()
    _child(str(slow_config(tmp_path, 0)), "run_helpers", sent)
    assert sent.closed
    ((kind, folder, record),) = sent.messages
    assert (kind, Path(str(folder))) == ("recorded", tmp_path / "out" / "slow")
    assert record["status"] == "success"  # type: ignore[index]
    refused = Sent()
    _child(str(tmp_path / "missing.toml"), "run_helpers", refused)
    assert refused.messages == [
        ("refused", f"ValidationError: config file {tmp_path / 'missing.toml'} does not exist")
    ]
    assert refused.closed
    assert KINDS["slow"].name == "slow"


class Pipe:
    def __init__(self, error: type[BaseException] | None = None, ready: bool = True) -> None:
        self.error = error
        self.ready = ready

    def poll(self) -> bool:
        return self.ready

    def recv(self) -> object:
        if self.error is not None:
            raise self.error
        return ("refused", "x")


def test_receiving_from_a_pipe() -> None:
    assert _receive(Pipe()) == ("refused", "x")
    assert _receive(Pipe(ready=False)) is None
    assert _receive(Pipe(EOFError)) is None
    assert _receive(Pipe(OSError)) is None


class Process:
    def __init__(self, alive: list[bool]) -> None:
        self.alive = alive  # what is_alive answers, in turn
        self.calls: list[str] = []

    def is_alive(self) -> bool:
        return self.alive.pop(0)

    def terminate(self) -> None:
        self.calls.append("terminate")

    def kill(self) -> None:
        self.calls.append("kill")

    def join(self, timeout: float | None = None) -> None:
        self.calls.append(f"join {timeout}")


def test_ending_a_process() -> None:
    gone = Process([False])
    assert end_process(gone) is False
    assert gone.calls == []
    polite = Process([True, False])
    assert end_process(polite, 2.0) is False
    assert polite.calls == ["terminate", "join 2.0"]
    stubborn = Process([True, True])
    assert end_process(stubborn, 2.0) is True
    assert stubborn.calls == ["terminate", "join 2.0", "kill", "join None"]
