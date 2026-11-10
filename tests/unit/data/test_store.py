"""Raw store: byte-for-byte storage with provenance, vintages and integrity checks.

All tests use temporary directories and a fake fetcher: no network, no real data.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.data.errors import DataNotFoundError, IntegrityError
from qrlab.data.provenance import Provenance
from qrlab.data.store import RawStore, download

T0 = datetime(2026, 11, 10, 15, 30, 0, tzinfo=UTC)
URL = "https://example.org/files/sample.zip"


def _prov(content: bytes, *, at: datetime = T0, dataset: str = "sample") -> Provenance:
    return Provenance(
        source="test_source",
        dataset=dataset,
        url=URL,
        retrieved_at=at,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="synthetic test data",
    )


class FakeFetcher:
    """Returns fixed bytes and records the URLs requested."""

    def __init__(self, content: bytes) -> None:
        self.content = content
        self.urls: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.urls.append(url)
        return self.content


# --------------------------------------------------------------------------- Provenance
def test_provenance_round_trips_through_json() -> None:
    p = _prov(b"abc")
    assert Provenance.from_json(p.to_json()) == p


def test_provenance_json_is_human_readable() -> None:
    record = json.loads(_prov(b"abc").to_json())
    assert record["retrieved_at"] == "2026-11-10T15:30:00+00:00"
    assert record["sha256"] == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.parametrize(
    "at",
    [datetime(2026, 11, 10, 15, 30), datetime(2026, 11, 10, tzinfo=timezone(timedelta(hours=1)))],
    ids=["naive", "non-utc"],
)
def test_provenance_requires_utc(at: datetime) -> None:
    with pytest.raises(ValidationError, match="UTC"):
        _prov(b"abc", at=at)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sha256", "XYZ"),
        ("size_bytes", -1),
        ("source", "../escape"),
        ("dataset", "a/b"),
        ("url", "ftp://example.org/x"),
        ("url", "file:C:/Users/someone/prices.csv"),
        ("url", "file:"),
        ("url", None),
    ],
)
def test_provenance_rejects_invalid_fields(field: str, value: object) -> None:
    fields = _prov(b"abc").__dict__ | {field: value}
    with pytest.raises(ValidationError):
        Provenance(**fields)


# --------------------------------------------------------------------------- put / read
def test_put_stores_bytes_unchanged_with_sidecar(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    content = b"raw,bytes\n1,2\n"
    stored = store.put(content, _prov(content))
    assert stored.path.read_bytes() == content
    assert stored.path.parent == tmp_path / "raw" / "test_source" / "sample"
    assert stored.path.name == f"20261110T153000Z_{hashlib.sha256(content).hexdigest()[:12]}.zip"
    sidecar = stored.path.with_name(stored.path.name + ".provenance.json")
    assert Provenance.from_json(sidecar.read_text(encoding="utf-8")) == stored.provenance


def test_stored_files_are_read_only(tmp_path: Path) -> None:
    stored = RawStore(tmp_path).put(b"x", _prov(b"x"))
    assert not os.stat(stored.path).st_mode & stat.S_IWRITE


def test_put_rejects_hash_or_size_mismatch(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    with pytest.raises(IntegrityError, match="SHA-256"):
        store.put(b"y", _prov(b"x"))  # same size, different content
    wrong_size = _prov(b"x").__dict__ | {"size_bytes": 5}
    with pytest.raises(IntegrityError, match="size"):
        store.put(b"x", Provenance(**wrong_size))


def test_read_verifies_hash(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    stored = store.put(b"original", _prov(b"original"))
    assert store.read(stored) == b"original"
    os.chmod(stored.path, stat.S_IWRITE | stat.S_IREAD)
    stored.path.write_bytes(b"tampered")
    with pytest.raises(IntegrityError, match="SHA-256"):
        store.read(stored)


# --------------------------------------------------------------------------- vintages
def test_same_content_twice_keeps_one_vintage(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    first = store.put(b"same", _prov(b"same"))
    second = store.put(b"same", _prov(b"same", at=T0 + timedelta(days=1)))
    assert second == first
    assert len(store.vintages("test_source", "sample")) == 1


def test_changed_content_creates_new_vintage_and_keeps_old(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    old = store.put(b"v1", _prov(b"v1"))
    new = store.put(b"v2", _prov(b"v2", at=T0 + timedelta(days=30)))
    assert store.vintages("test_source", "sample") == [old, new]
    assert store.latest("test_source", "sample") == new
    assert store.read(old) == b"v1"


def test_reverting_content_is_recorded_as_a_new_vintage(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.put(b"A", _prov(b"A"))
    store.put(b"B", _prov(b"B", at=T0 + timedelta(days=1)))
    again = store.put(b"A", _prov(b"A", at=T0 + timedelta(days=2)))
    assert len(store.vintages("test_source", "sample")) == 3
    assert store.latest("test_source", "sample") == again


def test_put_never_overwrites_an_existing_file(tmp_path: Path) -> None:
    # A stray file at the target path (e.g. copied in by hand, without a sidecar) is not
    # overwritten: the store refuses instead.
    store = RawStore(tmp_path)
    sha = hashlib.sha256(b"A").hexdigest()
    target = tmp_path / "raw" / "test_source" / "sample" / f"20261110T153000Z_{sha[:12]}.zip"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"stray")
    with pytest.raises(IntegrityError, match="exists"):
        store.put(b"A", _prov(b"A"))
    assert target.read_bytes() == b"stray"


def test_put_rejects_vintage_older_than_latest(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.put(b"A", _prov(b"A"))
    with pytest.raises(ValidationError, match="older"):
        store.put(b"B", _prov(b"B", at=T0 - timedelta(days=1)))


def test_latest_without_vintages_raises(tmp_path: Path) -> None:
    with pytest.raises(DataNotFoundError):
        RawStore(tmp_path).latest("test_source", "missing")


def test_vintages_of_unknown_dataset_is_empty(tmp_path: Path) -> None:
    assert RawStore(tmp_path).vintages("test_source", "missing") == []


def test_datasets_are_separate(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.put(b"A", _prov(b"A", dataset="one"))
    store.put(b"B", _prov(b"B", dataset="two"))
    assert store.read(store.latest("test_source", "one")) == b"A"
    assert store.read(store.latest("test_source", "two")) == b"B"


def test_extension_falls_back_to_bin(tmp_path: Path) -> None:
    fields = _prov(b"x").__dict__ | {"url": "https://example.org/api/data?format=csv"}
    stored = RawStore(tmp_path).put(b"x", Provenance(**fields))
    assert stored.path.suffix == ".bin"


# --------------------------------------------------------------------------- download
def test_download_fetches_hashes_and_stores(tmp_path: Path) -> None:
    fetcher = FakeFetcher(b"payload")
    stored = download(
        fetcher,
        RawStore(tmp_path),
        url=URL,
        source="test_source",
        dataset="sample",
        terms="synthetic",
        now=lambda: T0,
    )
    assert fetcher.urls == [URL]
    assert stored.provenance.sha256 == hashlib.sha256(b"payload").hexdigest()
    assert stored.provenance.size_bytes == 7
    assert stored.provenance.retrieved_at == T0


def test_download_rejects_empty_payload(tmp_path: Path) -> None:
    with pytest.raises(IntegrityError, match="empty"):
        download(
            FakeFetcher(b""),
            RawStore(tmp_path),
            url=URL,
            source="test_source",
            dataset="sample",
            terms="synthetic",
            now=lambda: T0,
        )
