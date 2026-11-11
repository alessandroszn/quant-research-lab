"""Append-only store of raw downloads with provenance.

Layout::

    <root>/raw/<source>/<dataset>/<YYYYMMDDTHHMMSSZ>_<sha256[:12]><ext>
    <root>/raw/<source>/<dataset>/<same name>.provenance.json

Rules: files are written once and set read-only; nothing is overwritten; a download identical to
the latest vintage is not stored again; a changed download becomes a new vintage and old
vintages are kept (sources such as the Ken French library revise history). Every read verifies
the SHA-256 recorded at download time.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from qrlab.core.errors import ValidationError
from qrlab.data.errors import DataNotFoundError, IntegrityError
from qrlab.data.fetch import Fetcher
from qrlab.data.provenance import Provenance

__all__ = ["RawStore", "StoredFile", "download"]

_SIDECAR = ".provenance.json"
_KNOWN_EXTENSIONS = frozenset({".zip", ".csv", ".txt", ".xml", ".json"})


@dataclass(frozen=True)
class StoredFile:
    """A raw file in the store and its provenance."""

    path: Path
    provenance: Provenance


class RawStore:
    """Append-only, integrity-checked store of raw files.

    Parameters
    ----------
    root
        Directory under which ``raw/`` is created, normally the git-ignored ``data/`` folder.
        Always passed explicitly; there is no default location.
    """

    def __init__(self, root: Path) -> None:
        self._raw = Path(root) / "raw"

    def put(self, content: bytes, provenance: Provenance) -> StoredFile:
        """Store ``content`` unless it equals the latest vintage, and return the stored file."""
        _check_matches(content, provenance)
        existing = self.vintages(provenance.source, provenance.dataset)
        if existing:
            latest = existing[-1]
            if latest.provenance.sha256 == provenance.sha256:
                return latest
            if provenance.retrieved_at < latest.provenance.retrieved_at:
                raise ValidationError(
                    f"vintage retrieved at {provenance.retrieved_at} is older than the latest "
                    f"({latest.provenance.retrieved_at})"
                )
        folder = self._folder(provenance.source, provenance.dataset)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = provenance.retrieved_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = folder / f"{stamp}_{provenance.sha256[:12]}{_extension(provenance.url)}"
        _write_once(path, content)
        _write_once(path.with_name(path.name + _SIDECAR), provenance.to_json().encode("utf-8"))
        return StoredFile(path=path, provenance=provenance)

    def vintages(self, source: str, dataset: str) -> list[StoredFile]:
        """Return all stored vintages of a dataset, oldest first (empty if none)."""
        folder = self._folder(source, dataset)
        if not folder.is_dir():
            return []
        files = []
        for sidecar in folder.glob(f"*{_SIDECAR}"):
            provenance = Provenance.from_json(sidecar.read_text(encoding="utf-8"))
            files.append(StoredFile(sidecar.with_name(sidecar.name[: -len(_SIDECAR)]), provenance))
        return sorted(files, key=lambda f: (f.provenance.retrieved_at, f.path.name))

    def latest(self, source: str, dataset: str) -> StoredFile:
        """Return the most recent vintage of a dataset."""
        found = self.vintages(source, dataset)
        if not found:
            raise DataNotFoundError(f"no stored vintage of {source}/{dataset} under {self._raw}")
        return found[-1]

    def read(self, stored: StoredFile) -> bytes:
        """Return the bytes of a stored file after verifying size and SHA-256."""
        content = stored.path.read_bytes()
        _check_matches(content, stored.provenance)
        return content

    def _folder(self, source: str, dataset: str) -> Path:
        return self._raw / source / dataset


def download(
    fetcher: Fetcher,
    store: RawStore,
    *,
    url: str,
    source: str,
    dataset: str,
    terms: str,
    now: Callable[[], datetime],
) -> StoredFile:
    """Fetch ``url``, record its provenance and store it.

    Parameters
    ----------
    fetcher
        Performs the download (a fake in tests).
    store
        Destination store.
    url, source, dataset, terms
        See :class:`~qrlab.data.provenance.Provenance`.
    now
        Clock returning the current UTC time, e.g. ``lambda: datetime.now(UTC)``. Explicit so
        that tests are deterministic.
    """
    content = fetcher.fetch(url)
    if not content:
        raise IntegrityError(f"download of {url} is empty; nothing stored")
    provenance = Provenance(
        source=source,
        dataset=dataset,
        url=url,
        retrieved_at=now(),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms=terms,
    )
    return store.put(content, provenance)


def _check_matches(content: bytes, provenance: Provenance) -> None:
    if len(content) != provenance.size_bytes:
        raise IntegrityError(
            f"size {len(content)} differs from recorded size {provenance.size_bytes}"
        )
    if hashlib.sha256(content).hexdigest() != provenance.sha256:
        raise IntegrityError("SHA-256 of the content differs from the recorded hash")


def _extension(url: str) -> str:
    suffix = PurePosixPath(urlparse(url).path).suffix.lower()
    return suffix if suffix in _KNOWN_EXTENSIONS else ".bin"


def _write_once(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise IntegrityError(f"{path} already exists; raw files are never overwritten") from exc
    os.chmod(path, stat.S_IREAD)
