"""The public API of ``qrlab.instruments`` is explicit and documented."""

from __future__ import annotations

import inspect
from collections.abc import Callable

import qrlab.instruments as instruments


def test_every_exported_name_exists_and_is_documented() -> None:
    for name in instruments.__all__:
        obj = getattr(instruments, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_report_thresholds_are_keyword_only_without_defaults() -> None:
    """Staleness and weight tolerances are always the caller's explicit choice."""
    cases: list[tuple[Callable[..., object], tuple[str, ...]]] = [
        (instruments.master_data_issues, ("on", "max_age_days")),
        (instruments.holdings_issues, ("on", "max_age_days", "weight_tolerance")),
    ]
    for func, params in cases:
        signature = inspect.signature(func)
        for param in params:
            assert signature.parameters[param].kind is inspect.Parameter.KEYWORD_ONLY
            assert signature.parameters[param].default is inspect.Parameter.empty
