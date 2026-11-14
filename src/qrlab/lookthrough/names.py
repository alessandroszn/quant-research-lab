"""Normalised security names, to match holdings across issuers when a file has no ISIN.

Two issuers may spell the same company differently ("APPLE INC" and "Apple Inc."). The key
removes accents, case, punctuation, a leading "THE" and trailing legal-form words, so that those
two compare equal. It is deliberately simple and is used only where an ISIN is missing; every
match it makes is labelled as approximate. Share classes ("CLASS A", "CLASS C") are kept, so
two lines of one company stay two securities.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["LEGAL_SUFFIXES", "name_key"]

LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {
        "AB", "AG", "AS", "ASA", "BHD", "BV", "CO", "COMPANY", "CORP", "CORPORATION", "GMBH",
        "INC", "INCORPORATED", "KGAA", "KK", "LIMITED", "LLC", "LP", "LTD", "NV", "OYJ", "PLC",
        "PTE", "PUBLIC", "SA", "SAB", "SE", "SPA", "TBK",
    }
)  # fmt: skip
"""Words removed from the end of a name (legal forms), after punctuation is removed."""

_DROPPED = re.compile("[.'\N{RIGHT SINGLE QUOTATION MARK}]")  # dots and apostrophes
_SEPARATORS = re.compile(r"[,;:()/\-]+")


def name_key(name: str) -> str:
    """Return the matching key of a security name.

    Accents are removed, letters upper-cased, dots and apostrophes dropped ("S.A." -> "SA"),
    other punctuation turned into spaces, a leading "THE" and trailing words of
    :data:`LEGAL_SUFFIXES` removed, and spaces collapsed. At least one word is always kept.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).upper()
    words = _SEPARATORS.sub(" ", _DROPPED.sub("", plain)).split()
    if len(words) > 1 and words[0] == "THE":
        words = words[1:]
    while len(words) > 1 and words[-1] in LEGAL_SUFFIXES:
        words = words[:-1]
    return " ".join(words)
