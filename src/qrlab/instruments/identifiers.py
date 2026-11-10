"""Instrument identifiers: ISIN (ISO 6166) and ISO 3166-1 alpha-2 country codes.

Validation never normalises input: lower-case letters, spaces or separators raise instead of
being fixed silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from qrlab.core.errors import ValidationError

__all__ = ["COUNTRIES", "ISIN_SPECIAL_PREFIXES", "Isin", "is_valid_isin", "validate_country"]

# One code per token, grouped by first letter for review against the ISO list.
COUNTRIES: frozenset[str] = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
    BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
    CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
    DE DJ DK DM DO DZ
    EC EE EG EH ER ES ET
    FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
    HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT
    JE JM JO JP
    KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY
    MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
    NA NC NE NF NG NI NL NO NP NR NU NZ
    OM
    PA PE PF PG PH PK PL PM PN PR PS PT PW PY
    QA
    RE RO RS RU RW
    SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
    TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ
    UA UG UM US UY UZ
    VA VC VE VG VI VN VU
    WF WS
    YE YT
    ZA ZM ZW
    """.split()  # noqa: SIM905 - 249 codes are easier to audit as a block
)
"""The 249 officially assigned ISO 3166-1 alpha-2 codes (list as of 2024)."""

ISIN_SPECIAL_PREFIXES: frozenset[str] = frozenset({"XS", "EU", "XA", "XB", "XC", "XD"})
"""ISIN prefixes that are not countries: international securities (XS), EU institutions (EU)
and substitute prefixes (XA-XD)."""

_ISIN_SHAPE = re.compile(r"^[A-Z0-9]{12}$")


@dataclass(frozen=True)
class Isin:
    """A validated International Securities Identification Number.

    Parameters
    ----------
    code
        Twelve characters: a two-letter prefix (ISO 3166-1 country or a special prefix), nine
        upper-case alphanumerics and a numeric check digit (Luhn on the letter-expanded code).
    """

    code: str

    def __post_init__(self) -> None:
        """Validate shape, prefix and check digit."""
        problem = _isin_problem(self.code)
        if problem:
            raise ValidationError(f"invalid ISIN {self.code!r}: {problem}")

    @property
    def prefix(self) -> str:
        """The two-letter prefix, usually the issuer's country."""
        return self.code[:2]

    def __str__(self) -> str:
        """Return the code."""
        return self.code


def is_valid_isin(code: str) -> bool:
    """Return whether ``code`` is a valid ISIN (no normalisation is applied)."""
    return _isin_problem(code) is None


def validate_country(code: object) -> str:
    """Return ``code`` if it is an ISO 3166-1 alpha-2 country code, else raise."""
    if not isinstance(code, str) or code not in COUNTRIES:
        raise ValidationError(f"{code!r} is not an ISO 3166-1 alpha-2 country code")
    return code


def _isin_problem(code: object) -> str | None:
    if not isinstance(code, str) or len(code) != 12:
        return "must be a string of 12 characters"
    if not _ISIN_SHAPE.match(code):
        return "only upper-case letters and digits are allowed"
    if not code[:2].isalpha():
        return "the first two characters must be letters"
    if code[:2] not in COUNTRIES and code[:2] not in ISIN_SPECIAL_PREFIXES:
        return f"unknown country prefix {code[:2]!r}"
    if not code[-1].isdigit():
        return "the check digit must be a digit"
    if _check_digit(code[:-1]) != int(code[-1]):
        return "wrong check digit"
    return None


def _check_digit(body: str) -> int:
    """Luhn check digit of the first 11 characters, letters expanded as A=10 ... Z=35."""
    digits = "".join(str(int(char, 36)) for char in body)
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - total % 10) % 10
