"""Overlap between funds whose files lack ISINs: matching by normalised name (design 8.2).

Hand values:

- **Names only.** Fund A = {APPLE INC 6 %, MICROSOFT CORP 5 %, NVIDIA CORP 4 %, ALPHA HOLDINGS
  PLC 85 %} and fund B = {Apple Inc. 5 %, Microsoft Corporation 6 %, Nvidia Corp. 2 %, Beta
  S.A. 87 %}, none with ISIN: overlap = min(6, 5) + min(5, 6) + min(4, 2) = 12 %, all by name.
- **Mixed.** Fund C = {Apple (ISIN P) 5 %, MICROSOFT CORP (ISIN M) 4 %, FOO CORP (ISIN F1) 1 %}
  and fund D = {Apple (ISIN P) 7 %, Microsoft Corp (no ISIN) 3 %, Foo Corp (ISIN F2) 1 %}:
  5 % by ISIN; 3 % by name, because D lists Microsoft without an ISIN; Foo is not matched,
  because both funds give it an ISIN and the ISINs differ. Overlap 8 %.
- **Cash lines are never matched by name:** "Cash" 2 % in both funds adds nothing.
"""

from __future__ import annotations

import pytest

from qrlab.lookthrough import WeightTreatment, pair_overlap
from qrlab.lookthrough.names import name_key
from support.checks import A, B, C, D
from support.lookthrough import holding, security, snapshot

AS_REPORTED = WeightTreatment.AS_REPORTED
P, M, F1, F2 = (security("US", n) for n in (11, 12, 13, 14))


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Apple Inc.", "APPLE INC"),
        ("apple, inc", "APPLE INC"),
        ("Microsoft Corporation", "MICROSOFT CORP"),
        ("The Coca-Cola Company", "COCA COLA CO"),
        ("Nestlé S.A.", "NESTLE SA"),
        ("AT&T Inc", "AT&T INC."),
        ("  Toyota   Motor  Corp ", "TOYOTA MOTOR CORPORATION"),
        ("ASML Holding N.V.", "ASML HOLDING NV"),
        ("McDonald\N{RIGHT SINGLE QUOTATION MARK}s Corp", "MCDONALD'S CORP"),
    ],
)
def test_same_company_same_key(first: str, second: str) -> None:
    assert name_key(first) == name_key(second)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Apple Hospitality REIT Inc", "Apple Inc"),
        ("Alphabet Inc Class A", "Alphabet Inc Class C"),  # share classes stay distinct
        ("Alpha Holdings PLC", "Alpha PLC"),
    ],
)
def test_different_companies_different_keys(first: str, second: str) -> None:
    assert name_key(first) != name_key(second)


def test_a_name_made_only_of_suffixes_is_kept() -> None:
    assert name_key("Inc.") == "INC"
    assert name_key("The Company") == "COMPANY"


def test_names_only_overlap_by_hand() -> None:
    first = snapshot(
        A,
        [
            holding("APPLE INC", 0.06),
            holding("MICROSOFT CORP", 0.05),
            holding("NVIDIA CORP", 0.04),
            holding("ALPHA HOLDINGS PLC", 0.85),
        ],
    )
    second = snapshot(
        B,
        [
            holding("Apple Inc.", 0.05),
            holding("Microsoft Corporation", 0.06),
            holding("Nvidia Corp.", 0.02),
            holding("Beta S.A.", 0.87),
        ],
    )
    result = pair_overlap(first, second, treatment=AS_REPORTED)
    assert result.overlap == pytest.approx(0.12)
    assert result.by_name == pytest.approx(0.12)
    assert result.unmatched_first == pytest.approx(1.0)  # no ISIN anywhere
    assert result.unmatched_second == pytest.approx(1.0)


def test_mixed_overlap_by_hand() -> None:
    first = snapshot(
        C,
        [
            holding("Apple Inc", 0.05, isin=P),
            holding("MICROSOFT CORP", 0.04, isin=M),
            holding("FOO CORP", 0.01, isin=F1),
            holding("Cash", 0.02, asset_class="cash"),
        ],
    )
    second = snapshot(
        D,
        [
            holding("APPLE INC", 0.07, isin=P),
            holding("Microsoft Corp", 0.03),
            holding("Foo Corp", 0.01, isin=F2),
            holding("Cash", 0.02, asset_class="cash"),
        ],
    )
    result = pair_overlap(first, second, treatment=AS_REPORTED)
    assert result.overlap == pytest.approx(0.08)
    assert result.by_name == pytest.approx(0.03)
    assert result.unmatched_first == pytest.approx(0.02)  # the cash line
    assert result.unmatched_second == pytest.approx(0.05)  # Microsoft and the cash line


def test_isin_overlap_is_unchanged_and_has_nothing_by_name() -> None:
    first = snapshot(A, [holding("X", 0.5, isin=P), holding("Y", 0.5, isin=M)])
    second = snapshot(B, [holding("X", 0.4, isin=P), holding("Z", 0.6, isin=F1)])
    result = pair_overlap(first, second, treatment=AS_REPORTED)
    assert result.overlap == pytest.approx(0.4)
    assert result.by_name == 0.0
