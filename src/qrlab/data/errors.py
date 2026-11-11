"""Errors specific to data access."""

from __future__ import annotations

from qrlab.core.errors import QrlabError, ValidationError

__all__ = ["DataNotFoundError", "FetchError", "IntegrityError", "ParseError"]


class DataNotFoundError(QrlabError, LookupError):
    """A requested dataset or vintage is not in the store."""


class FetchError(QrlabError):
    """A download failed or was refused (e.g. a non-HTTPS URL)."""


class IntegrityError(QrlabError):
    """Stored bytes do not match their recorded hash or size, or a file would be overwritten."""


class ParseError(ValidationError):
    """A source file does not have the expected format; nothing is guessed."""
