"""The public API of ``qrlab.portfolio`` is explicit and its conventions are keyword-only."""

from __future__ import annotations

import inspect

import qrlab.portfolio as portfolio


def test_every_exported_name_is_documented() -> None:
    for name in portfolio.__all__:
        obj = getattr(portfolio, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_conventions_are_keyword_only_without_defaults() -> None:
    """Base currency, converter, timing, dates and staleness limits are always explicit."""
    conventions = {"base", "to_base", "flow_timing", "dates", "max_price_age_days", "start", "end"}
    checked = 0
    for name in portfolio.__all__:
        obj = getattr(portfolio, name)
        if not inspect.isfunction(obj):
            continue
        for param in inspect.signature(obj).parameters.values():
            if param.name in conventions and param.kind is inspect.Parameter.KEYWORD_ONLY:
                checked += 1
                assert param.default is inspect.Parameter.empty, f"{name}.{param.name}"
    assert checked >= 8
