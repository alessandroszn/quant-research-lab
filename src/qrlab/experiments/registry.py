"""Experiment kinds: a name, what they need, how to parse parameters and how to run.

A kind is a thin adapter over tested library functions. ``parse`` validates the kind's
``[parameters]`` and returns a typed object; ``run`` receives a :class:`RunContext` and returns an
:class:`ExperimentOutput` whose every table and scalar is tagged ``in_sample``, ``out_of_sample``
or ``descriptive``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.experiments.config import ExperimentConfig

__all__ = ["TAGS", "ExperimentKind", "ExperimentOutput", "RunContext", "Tagged"]

TAGS = frozenset({"in_sample", "out_of_sample", "descriptive"})


@dataclass(frozen=True)
class Tagged:
    """A table or a scalar with its sample tag."""

    value: pd.DataFrame | float | str
    tag: str

    def __post_init__(self) -> None:
        """Check the tag."""
        if self.tag not in TAGS:
            raise ValidationError(f"tag must be one of {sorted(TAGS)}, got {self.tag!r}")


@dataclass(frozen=True)
class ExperimentOutput:
    """Everything a run produces (written by the runner, never by the kind)."""

    tables: Mapping[str, Tagged] = field(default_factory=dict)
    scalars: Mapping[str, Tagged] = field(default_factory=dict)
    figures: Mapping[str, bytes] = field(default_factory=dict)
    report_html: str | None = None
    notice: str | None = None
    """Short plain text that travels with the outputs (``NOTICE.txt``, the record, the CLI)."""


@dataclass(frozen=True)
class RunContext:
    """What a kind's ``run`` receives."""

    config: ExperimentConfig
    parameters: object
    inputs: Mapping[str, Path]
    seed: int | None


@dataclass(frozen=True)
class ExperimentKind:
    """A registered experiment kind."""

    name: str
    description: str
    inputs: tuple[str, ...]
    needs_seed: bool
    parameters: tuple[str, ...]
    parse: Callable[[Mapping[str, object]], object]
    run: Callable[[RunContext], ExperimentOutput]
    optional_inputs: tuple[str, ...] = ()  # files a config may give; absent ones are not in inputs
