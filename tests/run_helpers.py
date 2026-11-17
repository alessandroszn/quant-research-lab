"""Helpers for the run queue's tests (design note 12.2b).

- :class:`InlineStarter` runs a config in this process when its handle is first polled, so
  the app's screens can be tested quickly and deterministically.
- :data:`KINDS` holds a ``slow`` kind that sleeps for ``seconds``: a child process imports this
  module by name (``ProcessStarter("run_helpers")``) to have a run that is still running when
  it is cancelled.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pandas as pd

from qrlab.experiments import (
    ExperimentKind,
    ExperimentOutput,
    RunContext,
    Tagged,
    require_keys,
    run_experiment,
)
from qrlab.experiments.kinds import KINDS as LIBRARY_KINDS
from qrlab_app.runs import Outcome


def _parse(parameters: Mapping[str, object]) -> float:
    require_keys(parameters, required={"seconds"}, optional=set(), where="[parameters]")
    return float(cast(float, parameters["seconds"]))


def _run(context: RunContext) -> ExperimentOutput:
    time.sleep(cast(float, context.parameters))
    table = pd.DataFrame({"x": [1.0, 2.0]})
    return ExperimentOutput(tables={"slept": Tagged(table, "descriptive")})


SLOW = ExperimentKind("slow", "Sleep, then write a table", (), False, ("seconds",), _parse, _run)
KINDS = {**LIBRARY_KINDS, "slow": SLOW}


def slow_config(folder: Path, seconds: float, *, name: str = "slow") -> Path:
    """Write a config of the ``slow`` kind in ``folder``; its outputs go to ``out/<name>``."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.toml"
    path.write_text(
        f'[experiment]\nname = "{name}"\nkind = "slow"\nhypothesis = "descriptive"\n\n'
        f"[inputs]\n\n[parameters]\nseconds = {seconds}\n\n"
        f'[output]\ndirectory = "out/{name}"\n',
        encoding="utf-8",
    )
    return path


class InlineHandle:
    """A run done in this process, the first time it is polled."""

    def __init__(self, config: Path, kinds: Mapping[str, ExperimentKind]) -> None:
        self.config = config
        self.kinds = kinds
        self.outcome: Outcome | None = None
        self.cancelled = False

    def poll(self) -> Outcome | None:
        if self.outcome is None:
            try:
                result = run_experiment(self.config, kinds=self.kinds, overwrite=True)
            except Exception as exc:  # refused before a record, as the child reports it
                self.outcome = Outcome(error=f"{type(exc).__name__}: {exc}")
            else:
                self.outcome = Outcome(result=result)
        return self.outcome

    def cancel(self) -> None:
        self.cancelled = True


class InlineStarter:
    """Start runs in this process (see :class:`InlineHandle`)."""

    def __init__(self, kinds: Mapping[str, ExperimentKind] = KINDS) -> None:
        self.kinds = kinds
        self.handles: list[InlineHandle] = []

    def __call__(self, config: Path) -> InlineHandle:
        handle = InlineHandle(config, self.kinds)
        self.handles.append(handle)
        return handle
