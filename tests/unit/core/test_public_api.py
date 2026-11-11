"""The public API of ``qrlab.core`` is explicit and documented."""

from __future__ import annotations

import inspect
from collections.abc import Callable

import qrlab.core as core


def test_every_exported_name_exists() -> None:
    for name in core.__all__:
        assert hasattr(core, name), name


def test_every_exported_callable_has_a_docstring() -> None:
    for name in core.__all__:
        obj = getattr(core, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_conventions_are_keyword_only() -> None:
    """Return kind, NaN policy, frequency and minimum periods can never be passed by position."""
    cases: list[tuple[Callable[..., object], list[str]]] = [
        (core.validate_series, ["nan_policy"]),
        (core.validate_frame, ["nan_policy"]),
        (core.prices_to_returns, ["kind"]),
        (core.excess_returns, ["kind"]),
        (core.compound, ["kind"]),
        (core.wealth_index, ["kind", "initial"]),
        (core.aggregate_returns, ["kind", "to", "min_periods"]),
        (core.convert, ["to"]),
    ]
    for func, params in cases:
        signature = inspect.signature(func)
        for param in params:
            kind = signature.parameters[param].kind
            assert kind is inspect.Parameter.KEYWORD_ONLY, (
                f"{getattr(func, '__name__', func)}.{param}"
            )
            assert signature.parameters[param].default is inspect.Parameter.empty
