"""The public API of ``qrlab.scenarios`` is explicit and documented."""

from __future__ import annotations

import inspect

import qrlab.scenarios as scenarios


def test_every_exported_name_exists_and_is_documented() -> None:
    assert len(set(scenarios.__all__)) == len(scenarios.__all__)
    for name in scenarios.__all__:
        obj = getattr(scenarios, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name
