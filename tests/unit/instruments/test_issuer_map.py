"""Issuer map files (design 8.2).

Hand value: a fund held at 100 % lists two share classes of one company at 3 % and 2 %, and
other securities of 1 % each. Without a map the largest issuer is one share class, 3 %. With
the map, the two classes are one issuer: 3 + 2 = 5 %.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.instruments import load_issuer_map
from qrlab.instruments.identifiers import Isin
from qrlab.lookthrough import Dimension, WeightTreatment, look_through
from support.checks import A, fund
from support.lookthrough import holding, security, snapshot

CLASS_A, CLASS_C = security("US", 21), security("US", 22)
OTHERS = [security("US", 100 + n) for n in range(95)]


def _write(tmp: Path, text: str) -> Path:
    path = tmp / "issuers.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_map_joins_share_classes_by_hand(tmp_path: Path) -> None:
    issuers = load_issuer_map(
        _write(tmp_path, f"isin,issuer\n{CLASS_A},Example Holdings\n{CLASS_C},Example Holdings\n")
    )
    assert issuers == {Isin(CLASS_A): "Example Holdings", Isin(CLASS_C): "Example Holdings"}
    rows = [
        holding("Example Class A", 0.03, isin=CLASS_A),
        holding("Example Class C", 0.02, isin=CLASS_C),
        *(holding(f"Other {n}", 0.01, isin=isin) for n, isin in enumerate(OTHERS)),
    ]
    snap = snapshot(A, rows)

    def largest(mapping: dict[Isin, str] | None) -> tuple[str, float] | None:
        result = look_through(
            as_of=date(2026, 5, 31),
            position_weights={A: 1.0},
            cash_weights={},
            instruments={A: fund(A)},
            snapshots={A: snap},
            treatment=WeightTreatment.AS_REPORTED,
            issuers=mapping,
        )
        return result.largest(Dimension.ISSUER)

    without, mapped = largest(None), largest(issuers)
    assert without is not None
    assert mapped is not None
    assert without[0] == CLASS_A
    assert without[1] == pytest.approx(0.03)
    assert mapped[0] == "Example Holdings"
    assert mapped[1] == pytest.approx(0.05)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("isin;issuer\nX,Y\n", "header"),
        ("issuer,isin\n", "header"),
        ("isin,issuer\n", "no rows"),
        ("isin,issuer\nUS0000000000,Foo\n", "invalid ISIN"),
        (f"isin,issuer\n{CLASS_A},Foo\n{CLASS_A},Bar\n", "twice"),
        (f"isin,issuer\n{CLASS_A},  \n", "empty issuer"),
        (f"isin,issuer\n{CLASS_A},Foo,extra\n", "2 fields"),
    ],
)
def test_bad_maps_raise(tmp_path: Path, text: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        load_issuer_map(_write(tmp_path, text))


def test_a_byte_order_mark_and_blank_lines_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "issuers.csv"
    path.write_bytes(f"﻿isin,issuer\r\n{CLASS_A},Foo\r\n\r\n".encode())
    assert load_issuer_map(path) == {Isin(CLASS_A): "Foo"}
