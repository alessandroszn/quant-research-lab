"""Italian stamp duty and IVAFE (design note 11.3), with hand values.

Stamp duty (2 per mille, days / 365, rounded to €0.10 down up to €0.05, minimum €1):

- €10,000 held all of 2025 on yearly statements: 0.002 x 10,000 = €20.00;
- the same on quarterly statements: 20 x 90/365 = 4.93 -> 4.90, 20 x 91/365 = 4.99 -> 5.00,
  20 x 92/365 = 5.04 -> 5.00 twice: €19.90;
- an account opened on 2 December 2024: 20 x 30/365 = 1.64 -> 1.60;
- an account opened on 20 December 2025 with €1,000: 2 x 12/365 = 0.07 -> 0.10 -> €1.00.

IVAFE (0.20 %, days held / days of the year, ownership share):

- 100 units bought on 1 March 2025, 50 on 31 December: 306 days, 0.002 x 5,000 x 306/365 =
  €8.38;
- LIFO: 100 bought on 2 January, 50 on 1 July, 60 sold on 1 October at 45, 50 on 31
  December. The sale takes the 50 of July (92 days, 2,250) and 10 of January (272 days, 450);
  90 stay (364 days, 4,500): 0.002 / 365 x (207,000 + 122,400 + 1,638,000) = €10.78.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from qrlab.core.errors import ValidationError
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.transactions import Transaction, TransactionKind
from qrlab.tax.italy_wealth import (
    Custody,
    Statements,
    Where,
    lifo_lots,
    parse_custody,
    round_stamp_duty,
    wealth_taxes,
)
from support.portfolio import EUR, X, Y, eur_only, money, price_series, tx

K = TransactionKind
ITALY = {"main": Custody(Where.ITALY, Statements.YEAR, None)}
ABROAD = {"main": Custody(Where.ABROAD, None, Decimal(1))}


def _deposit(day: date, amount: str = "100000") -> Transaction:
    return tx(f"d{day}", day, K.DEPOSIT, amount=money(amount))


def _buy(day: date, units: str, price: str, isin: object = X) -> Transaction:
    return tx(f"b{day}{units}", day, K.BUY, isin=isin, quantity=units, price=money(price))  # type: ignore[arg-type]


def _sell(day: date, units: str, price: str) -> Transaction:
    return tx(f"s{day}{units}", day, K.SELL, isin=X, quantity=units, price=money(price))


def _run(transactions: list[Transaction], prices: dict[date, float], *, custody: object,
         as_of: date = date(2025, 12, 31), max_age: int = 0) -> object:  # fmt: skip
    history = replay(transactions, base=EUR, to_base=eur_only)
    return wealth_taxes(
        history=history,
        transactions=transactions,
        custody=custody,  # type: ignore[arg-type]
        prices={X: price_series(prices)} if prices else {},
        to_base=eur_only,
        max_price_age_days=max_age,
        as_of=as_of,
    )


def _items(result: object, year: int, tax: str) -> list[object]:
    return [i for i in result.items if i.year == year and i.tax == tax]  # type: ignore[attr-defined]


# ------------------------------------------------------------------------------ stamp duty
def test_stamp_duty_yearly_and_an_account_opened_in_december() -> None:
    txs = [_deposit(date(2024, 12, 2)), _buy(date(2024, 12, 2), "200", "50")]
    prices = {date(2024, 12, 2): 50.0, date(2024, 12, 31): 50.0, date(2025, 12, 31): 50.0}
    result = _run(txs, prices, custody=ITALY)
    (first,) = _items(result, 2024, "stamp_duty")
    assert (first.days, first.value, first.amount) == (30, Decimal(10000), Decimal("1.60"))  # type: ignore[attr-defined]
    (whole,) = _items(result, 2025, "stamp_duty")
    assert whole.amount == Decimal("20.00")  # type: ignore[attr-defined]
    assert [y.stamp_duty for y in result.years] == [Decimal("1.60"), Decimal("20.00")]  # type: ignore[attr-defined]


def test_stamp_duty_quarterly() -> None:
    txs = [_deposit(date(2024, 12, 2)), _buy(date(2024, 12, 2), "200", "50")]
    ends = [date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30),
            date(2025, 12, 31)]  # fmt: skip
    quarterly = {"main": Custody(Where.ITALY, Statements.QUARTER, None)}
    result = _run(txs, {date(2024, 12, 2): 50.0} | dict.fromkeys(ends, 50.0), custody=quarterly)
    amounts = [i.amount for i in _items(result, 2025, "stamp_duty")]  # type: ignore[attr-defined]
    assert amounts == [Decimal("4.90"), Decimal("5.00"), Decimal("5.00"), Decimal("5.00")]
    assert result.years[-1].stamp_duty == Decimal("19.90")  # type: ignore[attr-defined]


def test_monthly_periods_and_the_minimum() -> None:
    txs = [_deposit(date(2025, 12, 20)), _buy(date(2025, 12, 20), "20", "50")]
    monthly = {"main": Custody(Where.ITALY, Statements.MONTH, None)}
    result = _run(txs, {date(2025, 12, 20): 50.0, date(2025, 12, 31): 50.0}, custody=monthly)
    (item,) = _items(result, 2025, "stamp_duty")
    assert (item.days, item.amount) == (12, Decimal("1.00"))  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("amount", "rounded"),
    [
        ("3.6986", "3.70"),  # circolare 48/E's 2013 example at 1.5 per mille
        ("3.7397", "3.70"),
        ("3.7808", "3.80"),
        ("4.05", "4.00"),
        ("4.0501", "4.10"),
        ("0", "0.00"),
    ],
)
def test_stamp_duty_rounding(amount: str, rounded: str) -> None:
    assert round_stamp_duty(Decimal(amount)) == Decimal(rounded)


def test_no_securities_no_stamp_duty() -> None:
    txs = [_deposit(date(2024, 12, 2)), _buy(date(2024, 12, 2), "10", "50"),
           _sell(date(2024, 12, 20), "10", "50")]  # fmt: skip
    result = _run(txs, {date(2024, 12, 2): 50.0, date(2024, 12, 20): 50.0}, custody=ITALY)
    assert result.items == ()  # type: ignore[attr-defined]
    assert [y.stamp_duty for y in result.years] == [Decimal(0), Decimal(0)]  # type: ignore[attr-defined]
    assert _run([_deposit(date(2025, 1, 2))], {}, custody={}).years == ()  # type: ignore[attr-defined]


# ------------------------------------------------------------------------------------ IVAFE
def test_ivafe_one_lot() -> None:
    txs = [_deposit(date(2025, 3, 1)), _buy(date(2025, 3, 1), "100", "40")]
    result = _run(txs, {date(2025, 3, 1): 40.0, date(2025, 12, 31): 50.0}, custody=ABROAD)
    (item,) = _items(result, 2025, "ivafe")
    assert (item.days, item.value, item.amount) == (306, Decimal(5000), Decimal("8.38"))  # type: ignore[attr-defined]
    assert result.years[0].ivafe_payable == Decimal(0)  # type: ignore[attr-defined]  # 8.38 <= 12


def test_ivafe_lifo() -> None:
    txs = [
        _deposit(date(2025, 1, 2)),
        _buy(date(2025, 1, 2), "100", "40"),
        _buy(date(2025, 7, 1), "50", "42"),
        _sell(date(2025, 10, 1), "60", "45"),
    ]
    prices = {date(2025, 1, 2): 40.0, date(2025, 7, 1): 42.0, date(2025, 10, 1): 45.0,
              date(2025, 12, 31): 50.0}  # fmt: skip
    result = _run(txs, prices, custody=ABROAD)
    (item,) = _items(result, 2025, "ivafe")
    expected = Decimal("0.002") / 365 * (2250 * 92 + 450 * 272 + 4500 * 364)
    assert item.amount == expected.quantize(Decimal("0.01")) == Decimal("10.78")  # type: ignore[attr-defined]
    assert item.value == Decimal(7200)  # type: ignore[attr-defined]
    lots = sorted(lifo_lots(txs), key=lambda lot: (lot.acquired, lot.disposed or date.max))
    assert [(lot.acquired, lot.disposed, lot.units[-1][1]) for lot in lots] == [
        (date(2025, 1, 2), date(2025, 10, 1), Decimal(10)),
        (date(2025, 1, 2), None, Decimal(90)),
        (date(2025, 7, 1), date(2025, 10, 1), Decimal(50)),
    ]


def test_privileged_rate_share_threshold_and_leap_years() -> None:
    txs = [_deposit(date(2022, 12, 1)), _buy(date(2022, 12, 1), "100", "50")]
    prices = {date(2022, 12, 1): 50.0} | {date(y, 12, 31): 50.0 for y in (2022, 2023, 2024)}
    privileged = {"main": Custody(Where.ABROAD_PRIVILEGED, None, Decimal("0.5"))}
    result = _run(txs, prices, custody=privileged, as_of=date(2024, 12, 31))
    by_year = {y.year: y for y in result.years}  # type: ignore[attr-defined]
    assert by_year[2023].ivafe == Decimal("5.00")  # 0.20 % before 2024, half owned
    assert by_year[2024].ivafe == Decimal("10.00")  # 0.40 % from 2024; 366 / 366 days
    assert by_year[2024].ivafe_payable == Decimal(0)  # not above €12
    whole = {"main": Custody(Where.ABROAD_PRIVILEGED, None, Decimal(1))}
    full = {y.year: y for y in _run(txs, prices, custody=whole, as_of=date(2024, 12, 31)).years}  # type: ignore[attr-defined]
    assert full[2024].ivafe_payable == Decimal("20.00")


def test_a_split_scales_the_lot() -> None:
    txs = [
        _deposit(date(2025, 1, 2)),
        _buy(date(2025, 1, 2), "10", "50"),
        tx("split", date(2025, 6, 2), K.SPLIT, isin=X, quantity="2"),
    ]
    result = _run(txs, {date(2025, 1, 2): 50.0, date(2025, 12, 31): 25.0}, custody=ABROAD)
    (item,) = _items(result, 2025, "ivafe")
    assert item.value == Decimal(500)  # type: ignore[attr-defined]  # 20 units at 25


# ------------------------------------------------------------------------------ the years
def test_years_outside_the_checked_rules_are_not_computed() -> None:
    txs = [_deposit(date(2013, 12, 2)), _buy(date(2013, 12, 2), "10", "50")]
    prices = {date(2013, 12, 2): 50.0} | {date(y, 12, 31): 50.0 for y in range(2013, 2028)}
    result = _run(txs, prices, custody=ITALY, as_of=date(2028, 3, 1))
    assert result.not_computed == (2013, 2027)  # type: ignore[attr-defined]
    assert [y.year for y in result.years] == list(range(2014, 2027))  # type: ignore[attr-defined]
    current = _run(txs, prices, custody=ITALY, as_of=date(2025, 12, 30))
    assert current.years[-1].year == 2024  # type: ignore[attr-defined]  # 2025 has not ended


# ------------------------------------------------------------------------------- errors
def test_every_account_with_securities_needs_a_custody() -> None:
    txs = [_deposit(date(2025, 1, 2)), _buy(date(2025, 1, 2), "10", "50")]
    with pytest.raises(ValidationError, match=r"accounts are held: \['main'\]"):
        _run(txs, {date(2025, 1, 2): 50.0}, custody={"other": ITALY["main"]})


def test_a_missing_year_end_price_says_why() -> None:
    txs = [_deposit(date(2025, 1, 2)), _buy(date(2025, 1, 2), "10", "50")]
    with pytest.raises(ValidationError, match="max_price_age_days must reach"):
        _run(txs, {date(2025, 1, 2): 50.0, date(2025, 12, 30): 50.0}, custody=ITALY)
    result = _run(txs, {date(2025, 1, 2): 50.0, date(2025, 12, 30): 50.0}, custody=ITALY,
                  max_age=4)  # fmt: skip
    assert result.years[0].stamp_duty > 0  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="no price series"):
        _run(
            [*txs, _buy(date(2025, 1, 2), "1", "50", isin=Y)],
            {date(2025, 12, 31): 50.0},
            custody=ITALY,
        )


def test_a_sale_beyond_the_units_held_raises() -> None:
    with pytest.raises(ValidationError, match="beyond the units held"):
        lifo_lots([_buy(date(2025, 1, 2), "10", "50"), _sell(date(2025, 2, 3), "11", "50")])


def test_parse_custody() -> None:
    parsed = parse_custody({
        "Bank": {"where": "italy", "statements": "quarter"},
        "Broker": {"where": "abroad_privileged", "share": 0.5},
    })  # fmt: skip
    assert parsed["Bank"] == Custody(Where.ITALY, Statements.QUARTER, None)
    assert parsed["Broker"] == Custody(Where.ABROAD_PRIVILEGED, None, Decimal("0.5"))
    bad = [
        ({}, "one table per account"),
        ({"A": 1}, "must be a table"),
        ({"A": {"where": "moon"}}, "where must be one of"),
        ({"A": {"where": "italy"}}, r"missing \['statements'\]"),
        ({"A": {"where": "italy", "statements": "week"}}, "statements must be one of"),
        ({"A": {"where": "italy", "statements": "year", "share": 1}}, r"refused \['share'\]"),
        ({"A": {"where": "abroad", "share": 0}}, r"share must be a number in \(0, 1\]"),
        ({"A": {"where": "abroad", "share": True}}, "share must be a number"),
    ]
    for value, message in bad:
        with pytest.raises(ValidationError, match=message):
            parse_custody(value)


def test_a_lot_sold_in_an_earlier_year_pays_nothing_later() -> None:
    txs = [
        _deposit(date(2024, 12, 2)),
        _buy(date(2024, 12, 2), "10", "50"),
        _sell(date(2024, 12, 16), "10", "50"),
        _buy(date(2025, 3, 1), "100", "40"),
    ]
    prices = {date(2024, 12, 2): 50.0, date(2024, 12, 16): 50.0, date(2025, 3, 1): 40.0,
              date(2025, 12, 31): 50.0}  # fmt: skip
    result = _run(txs, prices, custody=ABROAD)
    (old,) = _items(result, 2024, "ivafe")
    assert (old.days, old.value) == (14, Decimal(500))  # type: ignore[attr-defined]
    (new,) = _items(result, 2025, "ivafe")
    assert new.amount == Decimal("8.38")  # type: ignore[attr-defined]  # only the 2025 lot


def test_the_italian_report_with_wealth_taxes() -> None:
    from qrlab.portfolio.valuation import Valuation
    from qrlab.tax.italy import (
        ITALY as REGIME,
    )
    from qrlab.tax.italy import (
        ItalianSettings,
        Regime,
        italian_tax_position,
        italian_tax_report,
    )
    from qrlab.tax.italy_wealth import WealthTaxes
    from qrlab.tax.regime import TaxInputs

    txs = [_deposit(date(2025, 1, 2))]
    history = replay(txs, base=EUR, to_base=eur_only)
    position = italian_tax_position(
        history, txs, {}, regime=Regime.AMMINISTRATO, public_share={},
        as_of=date(2025, 1, 2), to_base=eur_only,
    )  # fmt: skip
    report = italian_tax_report(position, WealthTaxes((), (), (2013,)))
    keys = [p.key for p in report.paragraphs]
    assert keys[-1] == "tax_sources"  # the wealth sentences come before the sources
    assert "tax_wealth_not_computed" in keys
    assert "stamp_duty_last_year" not in report.scalars
    assert any("D.L. 201/2011" in s for s in report.sources["en"])
    inputs = TaxInputs(history, txs, {}, Valuation(EUR, {}, {}, {}), eur_only, date(2025, 1, 2))
    settings = ItalianSettings(Regime.AMMINISTRATO, {}, ITALY)
    with pytest.raises(ValidationError, match="needs the report's prices"):
        REGIME.report(inputs, settings)
