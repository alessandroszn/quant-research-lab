"""ISIN check digits (ISO 6166) and ISO 3166-1 alpha-2 country codes.

Hand calculation for US0378331005 (from the approved design note): U = 30 and S = 28 give the
digit string 3028037833100; Luhn from the right, doubling every second digit starting with the
rightmost, sums to 45; the check digit is (10 - 45 mod 10) mod 10 = 5.
"""

from __future__ import annotations

import pytest

from qrlab.core.errors import ValidationError
from qrlab.instruments.identifiers import COUNTRIES, Isin, is_valid_isin, validate_country


@pytest.mark.parametrize(
    "code",
    [
        "US0378331005",  # hand-calculated above
        "IE00B4L5Y983",
        "LU0274208692",
        "XS0000000009",  # international prefix
        "EU000A2X2A25",  # EU prefix (the ECB's identifier for the euro short-term rate)
    ],
)
def test_valid_isins(code: str) -> None:
    assert is_valid_isin(code)
    assert Isin(code).code == code


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("IE00B4L5Y984", "check digit"),
        ("ie00b4l5y983", "upper-case"),
        ("IE00B4L5Y98", "12 characters"),
        ("IE00B4L5Y9833", "12 characters"),
        (" IE00B4L5Y983", "12 characters"),
        ("IE00-4L5Y983", "upper-case"),
        ("QQ0000000006", "country"),
        ("1E00B4L5Y983", "letters"),
        ("IE00B4L5Y98X", "check digit"),
    ],
)
def test_invalid_isins(code: str, reason: str) -> None:
    assert not is_valid_isin(code)
    with pytest.raises(ValidationError, match=reason):
        Isin(code)


def test_non_string_isin() -> None:
    assert not is_valid_isin(12345)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Isin(12345)  # type: ignore[arg-type]


def test_isin_country_prefix_and_str() -> None:
    isin = Isin("IE00B4L5Y983")
    assert isin.prefix == "IE"
    assert str(isin) == "IE00B4L5Y983"


def test_isin_equality_and_hash() -> None:
    assert Isin("IE00B4L5Y983") == Isin("IE00B4L5Y983")
    assert len({Isin("IE00B4L5Y983"), Isin("IE00B4L5Y983")}) == 1


def test_single_digit_change_is_always_detected() -> None:
    """The Luhn check catches every single-digit substitution."""
    base = "US0378331005"
    for position in range(2, 11):
        for digit in "0123456789":
            if digit == base[position]:
                continue
            mutated = base[:position] + digit + base[position + 1 :]
            assert not is_valid_isin(mutated), mutated


# --------------------------------------------------------------------------- countries
def test_country_table_is_complete_iso_3166_1() -> None:
    assert len(COUNTRIES) == 249
    assert {"IE", "LU", "DE", "FR", "IT", "US", "GB", "JP", "CN", "TW", "KR"} <= COUNTRIES
    assert all(len(code) == 2 and code.isupper() for code in COUNTRIES)


@pytest.mark.parametrize("code", ["IE", "US", "IT"])
def test_validate_country(code: str) -> None:
    assert validate_country(code) == code


@pytest.mark.parametrize("code", ["ie", "UK", "EU", "XS", "IRL", "", None])
def test_invalid_country(code: object) -> None:
    with pytest.raises(ValidationError, match="country"):
        validate_country(code)
