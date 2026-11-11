"""The public API of ``qrlab.lookthrough`` is explicit and documented."""

from __future__ import annotations

import inspect

import qrlab.lookthrough as lookthrough


def test_every_exported_name_exists_and_is_documented() -> None:
    assert len(set(lookthrough.__all__)) == len(lookthrough.__all__)
    for name in lookthrough.__all__:
        obj = getattr(lookthrough, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_builders_take_keyword_only_inputs_without_defaults() -> None:
    for function in (lookthrough.look_through,):
        for param in inspect.signature(function).parameters.values():
            assert param.kind is inspect.Parameter.KEYWORD_ONLY, param.name
            assert param.default is inspect.Parameter.empty, param.name
