"""URL fetcher (network replaced by a fake ``urlopen``) and the Dataset container."""

from __future__ import annotations

import hashlib
import io
import urllib.error
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import pytest

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.core.returns import ReturnKind
from qrlab.data.errors import FetchError
from qrlab.data.fetch import UrlFetcher
from qrlab.data.provenance import Dataset, Provenance, Unit


# --------------------------------------------------------------------------- UrlFetcher
class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_fetcher_sends_user_agent_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _Response:
        seen["url"] = request.full_url
        seen["agent"] = request.get_header("User-agent")
        seen["timeout"] = timeout
        return _Response(b"content")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert UrlFetcher(timeout_seconds=12.5).fetch("https://example.org/a.csv") == b"content"
    assert seen == {
        "url": "https://example.org/a.csv",
        "agent": seen["agent"],
        "timeout": 12.5,
    }
    assert seen["agent"].startswith("qrlab/")


def test_fetcher_wraps_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_urlopen(request: Any, timeout: float) -> _Response:
        raise urllib.error.URLError("unreachable")

    monkeypatch.setattr("urllib.request.urlopen", failing_urlopen)
    with pytest.raises(FetchError, match="unreachable"):
        UrlFetcher(timeout_seconds=1).fetch("https://example.org/a.csv")


@pytest.mark.parametrize("url", ["http://example.org/a", "file:///etc/passwd", "example.org"])
def test_fetcher_accepts_https_only(url: str) -> None:
    with pytest.raises(FetchError, match="https"):
        UrlFetcher(timeout_seconds=1).fetch(url)


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan")])
def test_fetcher_requires_positive_finite_timeout(bad: float) -> None:
    with pytest.raises(ValidationError, match="timeout"):
        UrlFetcher(timeout_seconds=bad)


# --------------------------------------------------------------------------- Dataset
def _provenance() -> Provenance:
    return Provenance(
        source="test_source",
        dataset="sample",
        url="https://example.org/sample.csv",
        retrieved_at=datetime(2026, 11, 10, tzinfo=UTC),
        sha256=hashlib.sha256(b"x").hexdigest(),
        size_bytes=1,
        terms="synthetic",
    )


def _frame() -> pd.DataFrame:
    idx = pd.DatetimeIndex(["2026-01-31", "2026-02-28"])
    return pd.DataFrame({"a": [0.01, np.nan]}, index=idx)


def test_dataset_holds_validated_copy() -> None:
    frame = _frame()
    ds = Dataset(
        data=frame,
        provenance=_provenance(),
        frequency=Frequency.MONTHLY,
        unit=Unit.RETURN,
        return_kind=ReturnKind.SIMPLE,
        currency=Currency("USD"),
        availability="test",
        notes=("synthetic",),
    )
    assert ds.data is not frame
    pd.testing.assert_frame_equal(ds.data, frame)


def test_dataset_rejects_invalid_data() -> None:
    unsorted = _frame().iloc[::-1]
    with pytest.raises(ValidationError, match="increasing"):
        Dataset(
            data=unsorted,
            provenance=_provenance(),
            frequency=Frequency.MONTHLY,
            unit=Unit.RETURN,
            return_kind=None,
            currency=None,
            availability="test",
            notes=(),
        )


def test_return_kind_is_required_for_returns_and_only_for_returns() -> None:
    with pytest.raises(ValidationError, match="return_kind"):
        Dataset(
            data=_frame(),
            provenance=_provenance(),
            frequency=Frequency.MONTHLY,
            unit=Unit.FX_RATE,
            return_kind=ReturnKind.SIMPLE,
            currency=None,
            availability="test",
            notes=(),
        )


def test_dataset_returns_require_return_kind() -> None:
    with pytest.raises(ValidationError, match="return_kind"):
        Dataset(
            data=_frame(),
            provenance=_provenance(),
            frequency=Frequency.MONTHLY,
            unit=Unit.RETURN,
            return_kind=None,
            currency=None,
            availability="test",
            notes=(),
        )
