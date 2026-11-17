"""The run queue: runs one after another, each in its own process (design note 12.2b).

:class:`RunQueue` is Qt-free. It keeps the session's runs in order and starts one at a time
through a *starter*, a callable that takes a config path and returns a :class:`RunHandle`.
The app's starter, :class:`ProcessStarter`, runs ``qrlab.experiments.run_experiment`` in a
child process, so cancelling a run ends its process at once, whatever it is computing. The
runner's staging folder keeps the earlier outputs safe (design note 12.2a); the queue deletes
the staging folder of a run it ends.

The app calls :meth:`RunQueue.step` from a timer; nothing here blocks.
"""

from __future__ import annotations

import importlib
import multiprocessing
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from qrlab.experiments import RunResult, file_sha256, load_config, run_experiment, staging_dir
from qrlab_app.strings import tr
from qrlab_app.viewmodels import AppError

__all__ = [
    "ACTIVE",
    "CANCELLED",
    "DONE",
    "FAILED",
    "KILL_AFTER_SECONDS",
    "RUNNING",
    "WAITING",
    "Outcome",
    "ProcessHandle",
    "ProcessStarter",
    "QueueEntry",
    "RunHandle",
    "RunQueue",
    "RunStarter",
    "end_process",
]

WAITING, RUNNING, DONE, FAILED, CANCELLED = "waiting", "running", "done", "failed", "cancelled"
ACTIVE = frozenset({WAITING, RUNNING})
KILL_AFTER_SECONDS = 5.0
"""How long a cancelled process may take to end before it is killed."""


@dataclass(frozen=True)
class Outcome:
    """How a run ended: recorded (``result``), refused before a record, or its process died."""

    result: RunResult | None = None
    error: str | None = None
    exit_code: int | None = None


class RunHandle(Protocol):
    """A started run."""

    def poll(self) -> Outcome | None:
        """Return the outcome once the run has ended, ``None`` while it runs."""

    def cancel(self) -> None:
        """End the run now."""


RunStarter = Callable[[Path], RunHandle]
"""Start the run of a config and return its handle."""


@dataclass(eq=False)
class QueueEntry:
    """One run of the session: its config, its state and how it ended."""

    number: int
    config: Path
    name: str
    kind: str
    output_dir: Path
    config_sha256: str
    state: str = WAITING
    note: tuple[str, dict[str, object]] | None = None  # a string key and its values
    result: RunResult | None = None
    started: float | None = None
    finished: float | None = None
    handle: RunHandle | None = field(default=None, repr=False)

    def note_text(self, language: str) -> str:
        """Return the entry's note in ``language`` (empty when there is none)."""
        return "" if self.note is None else tr(self.note[0], language, **self.note[1])


class RunQueue:
    """The session's runs, started one at a time, in the order they were added."""

    def __init__(self, start: RunStarter, *, clock: Callable[[], float] = time.monotonic) -> None:
        """Start runs with ``start``; ``clock`` gives seconds for the elapsed times."""
        self._start = start
        self._clock = clock
        self.entries: list[QueueEntry] = []

    # ----------------------------------------------------------------------- reading
    def active(self) -> list[QueueEntry]:
        """Return the running entry, if any, then the waiting ones, in order."""
        running = [e for e in self.entries if e.state == RUNNING]
        return running + [e for e in self.entries if e.state == WAITING]

    def latest(self, config: Path) -> QueueEntry | None:
        """Return the last entry of ``config``, or ``None``."""
        found = [e for e in self.entries if e.config == Path(config).resolve()]
        return found[-1] if found else None

    def position(self, entry: QueueEntry) -> int:
        """Return the place in line: 1 for the running entry; 0 when it is not active."""
        active = self.active()
        return active.index(entry) + 1 if entry in active else 0

    def elapsed(self, entry: QueueEntry) -> int:
        """Return the whole seconds the entry has run (so far, or in all)."""
        if entry.started is None:
            return 0
        end = self._clock() if entry.finished is None else entry.finished
        return int(end - entry.started)

    # ----------------------------------------------------------------------- changing
    def add(self, config: Path) -> QueueEntry:
        """Put a config in line; it runs as the file is now.

        Raises
        ------
        AppError
            When the config cannot be read, or an active entry writes the same output folder.
        """
        try:
            loaded = load_config(Path(config))
            digest = file_sha256(loaded.path)
        except (ValueError, OSError) as exc:  # ValidationError or a vanished file
            raise AppError("queue.unreadable", error=str(exc)) from exc
        for other in self.active():
            if other.output_dir == loaded.output_dir:
                raise AppError("queue.same_output", other=other.config.name)
        entry = QueueEntry(
            number=len(self.entries) + 1,
            config=loaded.path,
            name=loaded.name,
            kind=loaded.kind,
            output_dir=loaded.output_dir,
            config_sha256=digest,
        )
        self.entries.append(entry)
        return entry

    def step(self) -> list[QueueEntry]:
        """Collect the running entry's outcome and start the next one; return what changed."""
        changed: list[QueueEntry] = []
        running = next((e for e in self.entries if e.state == RUNNING), None)
        if running is not None:
            assert running.handle is not None  # set when it started
            outcome = running.handle.poll()
            if outcome is None:
                return changed
            self._finish(running, outcome)
            changed.append(running)
        for entry in [e for e in self.entries if e.state == WAITING]:
            changed.append(entry)
            if self._unchanged(entry) and self._begin(entry):
                break
        return changed

    def cancel(self, entry: QueueEntry) -> None:
        """Cancel a waiting entry, or end a running one; a finished entry is left as it is.

        A run that ended just before its process was ended keeps its outcome.
        """
        if entry.state == WAITING:
            self._close(entry, CANCELLED, ("queue.cancelled_waiting", {}))
        elif entry.state == RUNNING:
            assert entry.handle is not None  # set when it started
            entry.handle.cancel()
            outcome = entry.handle.poll()
            if outcome is not None and outcome.result is not None:
                self._finish(entry, outcome)
                if entry.state == DONE:
                    entry.note = ("queue.too_late", {})
                return
            _remove_staging(entry.output_dir)
            kept = (entry.output_dir / "record.json").exists()
            note = "queue.cancelled_kept" if kept else "queue.cancelled_none"
            self._close(entry, CANCELLED, (note, {}))

    def cancel_all(self) -> None:
        """Cancel every waiting and running entry."""
        for entry in reversed(self.active()):  # the waiting ones first: none starts
            self.cancel(entry)

    def clear_finished(self) -> None:
        """Drop the finished entries from the list (the runs stay in History)."""
        self.entries = [e for e in self.entries if e.state in ACTIVE]

    # ----------------------------------------------------------------------- helpers
    def _unchanged(self, entry: QueueEntry) -> bool:
        try:
            same = file_sha256(entry.config) == entry.config_sha256
        except OSError:
            same = False
        if not same:
            self._close(entry, FAILED, ("queue.changed", {}))
        return same

    def _begin(self, entry: QueueEntry) -> bool:
        try:
            entry.handle = self._start(entry.config)
        except Exception as exc:  # the process could not be started: reported, never raised
            self._close(entry, FAILED, ("queue.not_started", {"error": str(exc)}))
            return False
        entry.state = RUNNING
        entry.started = self._clock()
        return True

    def _finish(self, entry: QueueEntry, outcome: Outcome) -> None:
        if outcome.result is not None:
            entry.result = outcome.result
            if outcome.result.succeeded:
                self._close(entry, DONE, None)
            else:
                error = str(outcome.result.record.get("error"))
                self._close(entry, FAILED, ("queue.run_failed", {"error": error}))
            return
        _remove_staging(entry.output_dir)
        if outcome.exit_code is not None:
            self._close(entry, FAILED, ("queue.died", {"code": outcome.exit_code}))
        else:
            self._close(entry, FAILED, ("queue.refused", {"error": str(outcome.error)}))

    def _close(
        self, entry: QueueEntry, state: str, note: tuple[str, dict[str, object]] | None
    ) -> None:
        entry.state = state
        entry.note = note
        entry.handle = None
        entry.finished = self._clock()


def _remove_staging(output_dir: Path) -> None:
    shutil.rmtree(staging_dir(output_dir), ignore_errors=True)


# ------------------------------------------------------------------------------ processes
class _Process(Protocol):
    """What :func:`end_process` needs of a ``multiprocessing`` process."""

    def is_alive(self) -> bool: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...


class _Receiver(Protocol):
    """The receiving end of a pipe (``Connection``, or ``PipeConnection`` on Windows)."""

    def poll(self) -> bool: ...

    def recv(self) -> Any: ...


def end_process(process: _Process, wait: float = KILL_AFTER_SECONDS) -> bool:
    """End ``process``: terminate it, and kill it if it is still alive after ``wait`` seconds.

    Returns whether it had to be killed.
    """
    if not process.is_alive():
        return False
    process.terminate()
    process.join(wait)
    if not process.is_alive():
        return False
    process.kill()
    process.join()
    return True


def _child(config: str, kinds_module: str, send: Any) -> None:
    """Run one config in the child process and send back how it ended."""
    try:
        kinds = importlib.import_module(kinds_module).KINDS
        result = run_experiment(Path(config), kinds=kinds, overwrite=True)
    except Exception as exc:  # refused before a record: the message goes to the queue
        send.send(("refused", f"{type(exc).__name__}: {exc}"))
    else:
        send.send(("recorded", str(result.output_dir), dict(result.record)))
    finally:
        send.close()


class ProcessHandle:
    """A run in a child process (``multiprocessing``, *spawn*), with a pipe for its outcome."""

    def __init__(self, config: Path, kinds_module: str) -> None:
        """Start the child process."""
        context = multiprocessing.get_context("spawn")
        self._receive, send = context.Pipe(duplex=False)
        self.process = context.Process(
            target=_child, args=(str(config), kinds_module, send), daemon=True
        )
        self.process.start()
        send.close()  # the child holds the sending end
        self.killed = False

    def poll(self) -> Outcome | None:
        """Return the outcome once the process sent it or ended; ``None`` while it runs."""
        message = _receive(self._receive)
        if message is None and self.process.is_alive():
            return None
        if message is None:
            message = _receive(self._receive)  # sent just before it ended
        self.process.join(KILL_AFTER_SECONDS)
        if message is None:
            return Outcome(exit_code=self.process.exitcode)
        if message[0] == "recorded":
            return Outcome(result=RunResult(Path(message[1]), message[2]))
        return Outcome(error=str(message[1]))

    def cancel(self) -> None:
        """End the process now (it is killed if it does not end within a few seconds)."""
        self.killed = end_process(self.process)


def _receive(connection: _Receiver) -> tuple[Any, ...] | None:
    try:
        if connection.poll():
            message = connection.recv()
            assert isinstance(message, tuple)  # only _child sends
            return message
    except (EOFError, OSError):  # the child ended without sending
        return None
    return None


class ProcessStarter:
    """Start each run in its own process; the child takes its kinds from ``kinds_module``."""

    def __init__(self, kinds_module: str = "qrlab.experiments.kinds") -> None:
        """Use the kinds of ``kinds_module`` (a module with a ``KINDS`` mapping)."""
        self.kinds_module = kinds_module

    def __call__(self, config: Path) -> ProcessHandle:
        """Start the run of ``config``."""
        return ProcessHandle(config, self.kinds_module)
