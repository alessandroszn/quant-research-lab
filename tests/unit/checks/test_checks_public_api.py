"""The public API of ``qrlab.checks`` is explicit and documented."""

from __future__ import annotations

import inspect

import qrlab.checks as checks
from support.checks import AS_OF, A, weighted_context


def test_every_exported_name_exists_and_is_documented() -> None:
    assert len(set(checks.__all__)) == len(checks.__all__)
    for name in checks.__all__:
        obj = getattr(checks, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_result_carries_the_check_date() -> None:
    config = checks.CheckConfig(
        {
            spec.id: checks.Thresholds(False, 0.0, None, dict.fromkeys(spec.params, 0))
            for spec in checks.ALL_CHECKS
        }
    )
    result = checks.run_checks(weighted_context({A: "1"}), config)
    assert result.as_of == AS_OF
    assert len(result.disabled) == len(checks.ALL_CHECKS)
