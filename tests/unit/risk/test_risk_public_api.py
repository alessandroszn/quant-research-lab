"""The public API of ``qrlab.risk`` is explicit and documented."""

from __future__ import annotations

import inspect

import qrlab.risk as risk


def test_every_exported_name_exists_and_is_documented() -> None:
    assert len(set(risk.__all__)) == len(risk.__all__)
    for name in risk.__all__:
        obj = getattr(risk, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_conventions_are_keyword_only_without_defaults() -> None:
    for name in risk.__all__:
        obj = getattr(risk, name)
        if not inspect.isfunction(obj):
            continue
        for param in inspect.signature(obj).parameters.values():
            if param.kind is inspect.Parameter.KEYWORD_ONLY:
                assert param.default is inspect.Parameter.empty, (name, param.name)
