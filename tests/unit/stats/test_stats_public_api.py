"""The public API of ``qrlab.stats`` is explicit and its conventions are keyword-only."""

from __future__ import annotations

import inspect

import qrlab.stats as stats


def test_every_exported_name_is_documented() -> None:
    for name in stats.__all__:
        obj = getattr(stats, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_conventions_are_keyword_only_without_defaults() -> None:
    conventions = {
        "add_intercept", "cov_type", "hac_lags", "window", "model", "periods_per_year",
        "momentum_column", "mean_block_length", "n_resamples", "confidence", "rng",
    }  # fmt: skip
    checked = 0
    for name in stats.__all__:
        obj = getattr(stats, name)
        if not inspect.isfunction(obj):
            continue
        for param in inspect.signature(obj).parameters.values():
            if param.name in conventions:
                checked += 1
                assert param.kind is inspect.Parameter.KEYWORD_ONLY, f"{name}.{param.name}"
                assert param.default is inspect.Parameter.empty, f"{name}.{param.name}"
    assert checked >= 15
