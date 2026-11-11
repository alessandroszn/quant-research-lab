"""The public API of ``qrlab.metrics`` is explicit and its conventions are keyword-only."""

from __future__ import annotations

import inspect

import qrlab.metrics as metrics


def test_every_exported_name_is_documented() -> None:
    for name in metrics.__all__:
        obj = getattr(metrics, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_conventions_are_keyword_only_without_defaults() -> None:
    """periods_per_year, confidence, target, se_method and tolerances are never positional."""
    conventions = {"periods_per_year", "confidence", "target", "se_method", "weight_tolerance"}
    checked = 0
    for name in metrics.__all__:
        obj = getattr(metrics, name)
        if not inspect.isfunction(obj):
            continue
        for param in inspect.signature(obj).parameters.values():
            if param.name in conventions:
                checked += 1
                assert param.kind is inspect.Parameter.KEYWORD_ONLY, f"{name}.{param.name}"
                assert param.default is inspect.Parameter.empty, f"{name}.{param.name}"
    assert checked >= 20
