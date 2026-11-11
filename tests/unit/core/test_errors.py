"""The error hierarchy lets callers catch qrlab errors broadly or precisely."""

from __future__ import annotations

import pytest

from qrlab.core.errors import (
    AlignmentError,
    CurrencyError,
    CurrencyMismatchError,
    QrlabError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("error", "parents"),
    [
        (ValidationError, (QrlabError, ValueError)),
        (AlignmentError, (ValidationError, QrlabError, ValueError)),
        (CurrencyError, (QrlabError, ValueError)),
        (CurrencyMismatchError, (CurrencyError, QrlabError, ValueError)),
    ],
)
def test_hierarchy(error: type[Exception], parents: tuple[type[Exception], ...]) -> None:
    for parent in parents:
        assert issubclass(error, parent)


def test_alignment_is_not_a_currency_error() -> None:
    assert not issubclass(AlignmentError, CurrencyError)
    assert not issubclass(CurrencyMismatchError, ValidationError)
