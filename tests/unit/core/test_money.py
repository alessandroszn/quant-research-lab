"""Currency-aware amounts and dated FX conversion.

Hand calculations (from the approved design note):

- EUR 10.10 + EUR 0.20 = EUR 10.30 exactly (Decimal, not float)
- EUR/USD 1.25 means 1 EUR = 1.25 USD, so USD 100 -> EUR 80 and EUR 80 -> USD 100
- the inverse rate USD/EUR is 1 / 1.25 = 0.8
- JPY 1234.5 rounded half-even to 0 decimals -> JPY 1234
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pytest

from qrlab.core.errors import CurrencyError, CurrencyMismatchError
from qrlab.core.money import Currency, FxRate, Money, convert

EUR, USD, JPY = Currency("EUR"), Currency("USD"), Currency("JPY")
D = Decimal
DAY = date(2026, 11, 10)


# --------------------------------------------------------------------------- Currency
def test_currency_minor_units() -> None:
    assert EUR.minor_units == 2
    assert JPY.minor_units == 0
    assert Currency("KWD").minor_units == 3


@pytest.mark.parametrize("code", ["eur", "EURO", "XXX", "", "E1R"])
def test_unknown_or_malformed_codes_raise(code: str) -> None:
    with pytest.raises(CurrencyError):
        Currency(code)


def test_currency_equality_and_str() -> None:
    assert Currency("EUR") == EUR
    assert EUR != USD
    assert str(EUR) == "EUR"


# --------------------------------------------------------------------------- Money construction
def test_money_of_accepts_str_int_decimal_and_code() -> None:
    assert Money.of("10.10", "EUR") == Money(D("10.10"), EUR)
    assert Money.of(5, EUR).amount == D(5)
    assert Money.of(D("1.5"), "USD").currency == USD


def test_float_amounts_are_refused() -> None:
    with pytest.raises(CurrencyError, match="float"):
        Money(0.1, EUR)  # type: ignore[arg-type]
    with pytest.raises(CurrencyError, match="float"):
        Money.of(0.1, "EUR")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_amounts_are_refused(bad: str) -> None:
    with pytest.raises(CurrencyError, match="finite"):
        Money(D(bad), EUR)


def test_bool_amount_is_refused() -> None:
    with pytest.raises(CurrencyError):
        Money.of(True, "EUR")


def test_currency_must_be_currency_instance() -> None:
    with pytest.raises(CurrencyError):
        Money(D(1), "EUR")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- arithmetic
def test_addition_is_exact() -> None:
    assert Money.of("10.10", "EUR") + Money.of("0.20", "EUR") == Money.of("10.30", "EUR")
    assert Money.of("0.1", "EUR") + Money.of("0.2", "EUR") == Money.of("0.3", "EUR")


def test_mixing_currencies_raises() -> None:
    with pytest.raises(CurrencyMismatchError):
        _ = Money.of(1, "EUR") + Money.of(1, "USD")
    with pytest.raises(CurrencyMismatchError):
        _ = Money.of(1, "EUR") - Money.of(1, "USD")
    with pytest.raises(CurrencyMismatchError):
        _ = Money.of(1, "EUR") < Money.of(2, "USD")


def test_subtraction_negation_and_abs() -> None:
    a, b = Money.of("5.00", "EUR"), Money.of("7.50", "EUR")
    assert a - b == Money.of("-2.50", "EUR")
    assert -a == Money.of("-5.00", "EUR")
    assert abs(a - b) == Money.of("2.50", "EUR")


def test_scaling_by_int_and_decimal() -> None:
    a = Money.of("2.50", "EUR")
    assert a * 3 == Money.of("7.50", "EUR")
    assert 3 * a == Money.of("7.50", "EUR")
    assert a * D("0.5") == Money.of("1.25", "EUR")
    assert a / 2 == Money.of("1.25", "EUR")


def test_scaling_by_float_or_money_is_a_type_error() -> None:
    a = Money.of("2.50", "EUR")
    with pytest.raises(TypeError):
        _ = a * 1.5  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = a * a  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = a + 1  # type: ignore[operator]


def test_comparisons_within_currency() -> None:
    small, large = Money.of("1.00", "EUR"), Money.of("2.00", "EUR")
    assert small < large <= large
    assert large > small >= small
    assert Money.of("1.0", "EUR") == Money.of("1.00", "EUR")


def test_equality_across_currencies_is_false_not_an_error() -> None:
    assert Money.of(1, "EUR") != Money.of(1, "USD")


def test_money_is_hashable_and_immutable() -> None:
    a = Money.of("1.00", "EUR")
    assert len({a, Money.of("1.0", "EUR")}) == 1
    with pytest.raises(AttributeError):
        a.amount = D(2)  # type: ignore[misc]


# --------------------------------------------------------------------------- rounding
def test_rounding_to_minor_units() -> None:
    assert Money.of("1234.5", "JPY").rounded(ROUND_HALF_EVEN) == Money.of(1234, "JPY")
    assert Money.of("1234.5", "JPY").rounded(ROUND_HALF_UP) == Money.of(1235, "JPY")
    assert Money.of("2.345", "EUR").rounded(ROUND_HALF_EVEN).amount == D("2.34")
    assert Money.of("2.345", "EUR").rounded(ROUND_HALF_EVEN).amount.as_tuple().exponent == -2


def test_rounding_mode_must_be_valid() -> None:
    with pytest.raises(CurrencyError, match="rounding"):
        Money.of(1, "EUR").rounded("nearest")


def test_arithmetic_never_rounds_implicitly() -> None:
    third = Money.of(1, "EUR") / 3
    assert third.amount != D("0.33")


# --------------------------------------------------------------------------- FX
def test_fx_rate_convention_and_conversion() -> None:
    rate = FxRate(EUR, USD, D("1.25"), DAY)
    assert convert(Money.of(100, "USD"), rate, to=EUR) == Money.of(80, "EUR")
    assert convert(Money.of(80, "EUR"), rate, to=USD) == Money.of(100, "USD")


def test_fx_rate_invert() -> None:
    inverse = FxRate(EUR, USD, D("1.25"), DAY).invert()
    assert inverse == FxRate(USD, EUR, D("0.8"), DAY)


def test_convert_with_unrelated_rate_raises() -> None:
    rate = FxRate(EUR, USD, D("1.25"), DAY)
    with pytest.raises(CurrencyMismatchError):
        convert(Money.of(100, "JPY"), rate, to=EUR)
    with pytest.raises(CurrencyMismatchError):
        convert(Money.of(100, "EUR"), rate, to=JPY)
    with pytest.raises(CurrencyMismatchError):
        convert(Money.of(100, "EUR"), rate, to=EUR)


@pytest.mark.parametrize("bad", [D(0), D(-1), D("NaN"), D("Infinity")])
def test_fx_rate_must_be_positive_and_finite(bad: Decimal) -> None:
    with pytest.raises(CurrencyError, match="rate"):
        FxRate(EUR, USD, bad, DAY)


def test_fx_rate_refuses_float_same_currency_and_datetime() -> None:
    with pytest.raises(CurrencyError, match="float"):
        FxRate(EUR, USD, 1.25, DAY)  # type: ignore[arg-type]
    with pytest.raises(CurrencyError, match="differ"):
        FxRate(EUR, EUR, D(1), DAY)
    with pytest.raises(CurrencyError, match="date"):
        FxRate(EUR, USD, D("1.25"), datetime(2026, 11, 10, 16, 0))


def test_round_trip_conversion_is_exact_for_terminating_rates() -> None:
    rate = FxRate(EUR, USD, D("1.0825"), DAY)
    eur = Money.of("1234.56", "EUR")
    assert convert(convert(eur, rate, to=USD), rate, to=EUR) == eur
