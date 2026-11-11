"""The public API of ``qrlab.data`` is explicit, documented and offline by construction."""

from __future__ import annotations

import inspect

import qrlab.data as data


def test_every_exported_name_exists_and_is_documented() -> None:
    for name in data.__all__:
        obj = getattr(data, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert inspect.getdoc(obj), name


def test_parsers_take_bytes_not_fetchers() -> None:
    """Parsers are pure functions of bytes: none of them can reach the network."""
    for name in data.__all__:
        if name.startswith("parse_"):
            parameters = inspect.signature(getattr(data, name)).parameters
            assert "content" in parameters, name
            assert "fetcher" not in parameters, name


def test_downloads_take_an_explicit_clock() -> None:
    for name in ("download", "download_ken_french", "download_ecb_fx", "download_ecb_series"):
        parameter = inspect.signature(getattr(data, name)).parameters["now"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty
