"""Downloading raw bytes. Kept separate from parsing so parsers stay pure and testable offline."""

from __future__ import annotations

import importlib.metadata
import math
import urllib.error
import urllib.request
from typing import Protocol

from qrlab.core.errors import ValidationError
from qrlab.data.errors import FetchError

__all__ = ["Fetcher", "UrlFetcher"]


class Fetcher(Protocol):
    """Anything that returns the raw bytes found at a URL."""

    def fetch(self, url: str) -> bytes:
        """Return the bytes at ``url`` or raise :class:`~qrlab.data.errors.FetchError`."""
        ...


class UrlFetcher:
    """Fetch over HTTPS with the standard library.

    One attempt with an explicit timeout; errors surface instead of being retried silently.

    Parameters
    ----------
    timeout_seconds
        Socket timeout for the request.
    """

    def __init__(self, *, timeout_seconds: float) -> None:
        if not (math.isfinite(timeout_seconds) and timeout_seconds > 0):
            raise ValidationError(f"timeout must be positive and finite, got {timeout_seconds}")
        self._timeout = timeout_seconds

    def fetch(self, url: str) -> bytes:
        """Download ``url``; only ``https://`` URLs are accepted."""
        if not url.startswith("https://"):
            raise FetchError(f"only https URLs are allowed, got {url!r}")
        request = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                content: bytes = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchError(f"download of {url} failed: {exc}") from exc
        return content


def _user_agent() -> str:
    # Read from package metadata: subpackages must not import the root ``qrlab`` package.
    try:
        version = importlib.metadata.version("quant-research-lab")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - uninstalled tree only
        version = "unknown"
    return f"qrlab/{version}"
