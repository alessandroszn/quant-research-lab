"""Number, money, date and text formatting for reports. Hand examples from the design note."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.reporting.formatting import (
    EN,
    IT,
    Language,
    escape,
    format_date,
    format_money,
    format_number,
    format_percent,
    style_for,
)
from qrlab.reporting.labels import LABELS, label


@pytest.mark.parametrize(
    ("value", "decimals", "style", "expected"),
    [
        (1234.5, 2, IT, "1.234,50"),
        (1234.5, 2, EN, "1,234.50"),
        (Decimal("15480"), 2, IT, "15.480,00"),
        (-1234567.891, 1, IT, "-1.234.567,9"),
        (0.5, 0, EN, "1"),  # display rounding is half-up
        (2.5, 0, EN, "3"),
        (-0.0, 2, IT, "0,00"),
        (-0.001, 2, IT, "0,00"),  # rounds to zero: no "-0,00"
        (999.995, 2, EN, "1,000.00"),
        (42, 0, IT, "42"),
    ],
)
def test_format_number(value: float, decimals: int, style: object, expected: str) -> None:
    assert format_number(value, decimals, style=style) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, Decimal("NaN")])
def test_non_finite_numbers_raise(bad: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        format_number(bad, 2, style=IT)


def test_decimals_must_be_a_small_non_negative_int() -> None:
    for bad in (-1, 1.5, 13):
        with pytest.raises(ValidationError, match="decimals"):
            format_number(1.0, bad, style=IT)  # type: ignore[arg-type]


def test_format_percent() -> None:
    assert format_percent(0.0316558, 2, style=IT) == "3,17 %"
    assert format_percent(0.0316558, 2, style=EN) == "3.17%"
    assert format_percent(-0.06007, 1, style=IT) == "-6,0 %"


def test_format_money_uses_minor_units() -> None:
    assert format_money(Money.of("-1234.5", "EUR"), style=IT) == "-1.234,50 EUR"
    assert format_money(Money.of("1234.5", "EUR"), style=EN) == "EUR 1,234.50"
    assert format_money(Money.of("1234.5", "JPY"), style=IT) == "1.235 JPY"


def test_format_date() -> None:
    assert format_date(date(2026, 3, 31), language=Language.IT) == "31/03/2026"
    assert format_date(date(2026, 3, 31), language=Language.EN) == "2026-03-31"


def test_style_for_language() -> None:
    assert style_for(Language.IT) is IT
    assert style_for(Language.EN) is EN


def test_escape() -> None:
    assert escape('<script>alert("x")</script> & co') == (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; co"
    )


# --------------------------------------------------------------------------- labels
def test_both_languages_have_the_same_labels() -> None:
    assert set(LABELS[Language.IT]) == set(LABELS[Language.EN])
    assert all(text.strip() for texts in LABELS.values() for text in texts.values())


def test_label_lookup_and_unknown_key() -> None:
    assert label("disclaimer", Language.IT).startswith("Analisi")
    assert "not investment advice" in label("disclaimer", Language.EN)
    with pytest.raises(KeyError):
        label("no_such_label", Language.EN)


def test_numpy_scalars_are_formatted() -> None:
    """Regression: NumPy 2 scalars repr as "np.float64(...)", which Decimal cannot parse."""
    import numpy as np

    assert format_number(np.float64(1234.5), 2, style=IT) == "1.234,50"
    assert format_number(np.int64(7), 0, style=EN) == "7"
    assert format_percent(np.float32(0.25), 0, style=EN) == "25%"


def test_non_numbers_are_refused() -> None:
    with pytest.raises(ValidationError, match="booleans"):
        format_number(True, 0, style=EN)
    with pytest.raises(ValidationError, match="str"):
        format_number("12", 0, style=EN)  # type: ignore[arg-type]
