"""The public API of ``qrlab.reporting`` is explicit and documented."""

from __future__ import annotations

import inspect

import qrlab.reporting as reporting


def test_every_exported_name_is_documented() -> None:
    for name in reporting.__all__:
        obj = getattr(reporting, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


# Inputs added after the 1.0 API freeze default to ``None``, which keeps every earlier call
# valid (docs/compatibility.md); each one is listed here with its design note.
ADDED_AFTER_FREEZE = {"return_sources": "11.1", "benchmark": "11.2"}


def test_report_inputs_are_keyword_only_without_defaults() -> None:
    signature = inspect.signature(reporting.build_portfolio_report)
    for param in signature.parameters.values():
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, param.name
        if param.name in ADDED_AFTER_FREEZE:
            assert param.default is None, param.name
        else:
            assert param.default is inspect.Parameter.empty, param.name
    overwrite = inspect.signature(reporting.write_report).parameters["overwrite"]
    assert overwrite.kind is inspect.Parameter.KEYWORD_ONLY
    assert overwrite.default is inspect.Parameter.empty
