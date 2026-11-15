"""The configurable tax model (design 9.3), by hand. All data synthetic, EUR.

Settings: gains 20 %, income 25 %, losses netted and carried 2 years, gains on units held 12
months exempt, allowance 1,000, no wealth tax.

- **2025.** Buy 100 X at 100 on 2 January; sell 50 at 80 on 2 June (5 months): a loss of
  1,000, carried, usable until the end of 2027. No tax.
- **2026.**
  - Buy 100 Y at 50 on 5 January.
  - Sell the other 50 X at 150 on 1 February: 2,500, held 13 months, exempt.
  - Y pays 400 with 60 withheld on 15 February.
  - Sell the 100 Y at 80 on 1 March: 3,000, held 2 months, taxable.
  - Taxable 3,000 - 1,000 carried - 1,000 allowance = 1,000: tax 200. Income tax 100.
- **Losses ignored:** 3,000 - 1,000 = 2,000, tax 400. **Netted, no carry:** also 400.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.transactions import Transaction, TransactionKind
from qrlab.portfolio.valuation import value_portfolio
from qrlab.simulation.losses import LossRules
from qrlab.tax import REGIMES, TaxInputs, TaxReport, TaxTable
from qrlab.tax.custom import CUSTOM, custom_tax_model
from support.custom_account import TRANSACTIONS
from support.portfolio import price_series, tx

K = TransactionKind
EUR = Currency("EUR")
X, Y = Isin("IE0000000012"), Isin("US0000000044")


def eur(amount: str | int) -> Money:
    return Money.of(amount, "EUR")


def same(amount: Money, on: date) -> Money:
    return amount


TABLE: dict[str, object] = {
    "description": "Example country, my reading",
    "gains_rate": 0.20,
    "income_rate": 0.25,
    "losses": "netted",
    "loss_carry_years": 2,
    "exempt_after_months": 12,
    "gains_allowance": 1000,
    "wealth_tax_rate": 0.0,
}


def _inputs(rows: list[Transaction] | None = None, as_of: date = date(2026, 12, 31)) -> TaxInputs:
    rows = TRANSACTIONS if rows is None else rows
    history = replay(rows, base=EUR, to_base=same)
    days = sorted({date(2025, 12, 31), as_of})
    prices = {
        X: price_series(dict.fromkeys(days, 100.0)),
        Y: price_series(dict.fromkeys(days, 80.0)),
    }
    valuation = value_portfolio(history, prices, same, dates=days, max_price_age_days=0)
    return TaxInputs(history, rows, {}, valuation, same, as_of)


def _report(rows: list[Transaction] | None = None, **changes: object) -> TaxReport:
    return CUSTOM.report(_inputs(rows), CUSTOM.parse(TABLE | changes))


def _rows(report: TaxReport, file: str) -> list[dict[str, object]]:
    table: TaxTable = next(t for t in report.tables if t.file == file)
    return [dict(zip((c.key for c in table.columns), row, strict=True)) for row in table.rows]


def _year(report: TaxReport, year: int) -> dict[str, object]:
    return next(r for r in _rows(report, "custom_years") if r["year"] == year)


# --------------------------------------------------------------------------- by hand
def test_the_example_by_hand() -> None:
    report = _report()
    y2025, y2026 = _year(report, 2025), _year(report, 2026)
    assert (y2025["result"], y2025["taxable_losses"], y2025["gains_tax"]) == (-1000, 1000, 0)
    assert y2026["result"] == Decimal(5500)
    assert y2026["exempt"] == Decimal(2500)
    assert (y2026["taxable_gains"], y2026["losses_used"], y2026["allowance_used"]) == (
        Decimal(3000),
        Decimal(1000),
        Decimal(1000),
    )
    assert (y2026["taxable"], y2026["gains_tax"]) == (Decimal(1000), Decimal("200.00"))
    assert (y2026["income"], y2026["income_tax"], y2026["withheld"]) == (
        Decimal(400),
        Decimal("100.00"),
        Decimal(60),
    )
    (lot,) = _rows(report, "custom_losses")
    assert (lot["year"], lot["losses"], lot["used"], lot["remaining"]) == (2025, 1000, 1000, 0)
    assert lot["usable_until"] == date(2027, 12, 31)
    assert report.scalars == {
        "gains_tax_estimate": Decimal("200.00"),
        "income_tax_estimate": Decimal("100.00"),
        "wealth_tax_estimate": Decimal("0.00"),
        "losses_remaining": Decimal(0),
    }
    assert report.notice is not None
    assert "simplified model you configured" in report.notice


def test_losses_ignored() -> None:
    report = _report(losses="ignored", loss_carry_years=0)
    y2026 = _year(report, 2026)
    assert (y2026["losses_used"], y2026["taxable"], y2026["gains_tax"]) == (
        0,
        2000,
        Decimal("400.00"),
    )
    assert not any(t.file == "custom_losses" for t in report.tables)


def test_losses_netted_but_not_carried() -> None:
    report = _report(loss_carry_years=0)
    assert _year(report, 2026)["gains_tax"] == Decimal("400.00")
    (lot,) = _rows(report, "custom_losses")
    assert (lot["expired"], lot["remaining"], lot["usable_until"]) == (1000, 0, date(2025, 12, 31))


def test_a_partly_exempt_sale() -> None:
    """100 units of 2 January 2025 and 50 of 5 January 2026, all 150 sold on 1 March 2026.

    The 100 old ones are exempt: 2/3 of the 1,500 gain (150 x (110 - 100)) is 1,000.
    """
    rows = [
        tx("d", date(2025, 1, 2), K.DEPOSIT, amount=eur(20000)),
        tx("b1", date(2025, 1, 2), K.BUY, isin=X, quantity="100", price=eur(100)),
        tx("b2", date(2026, 1, 5), K.BUY, isin=X, quantity="50", price=eur(100)),
        tx("s", date(2026, 3, 1), K.SELL, isin=X, quantity="150", price=eur(110)),
    ]
    y2026 = _year(_report(rows), 2026)
    assert (y2026["result"], y2026["exempt"], y2026["taxable_gains"]) == (1500, 1000, 500)
    assert (y2026["allowance_used"], y2026["gains_tax"]) == (500, 0)  # never negative


def test_no_exemption_when_the_months_are_zero() -> None:
    y2026 = _year(_report(exempt_after_months=0), 2026)
    assert (y2026["exempt"], y2026["taxable_gains"]) == (0, 5500)


def test_the_wealth_tax_and_an_open_year() -> None:
    """On 31 Dec 2025: 50 X at 100 and cash 14,000 = 19,000; at 0.2 % the tax is 38."""
    inputs = _inputs(as_of=date(2026, 6, 30))
    report = CUSTOM.report(inputs, CUSTOM.parse(TABLE | {"wealth_tax_rate": 0.002}))
    assert (_year(report, 2025)["wealth"], _year(report, 2025)["wealth_tax"]) == (
        Decimal(19000),
        Decimal("38.00"),
    )
    assert _year(report, 2026)["wealth"] is None
    assert report.scalars["wealth_tax_estimate"] == Decimal("38.00")  # 2025, the latest ended


# --------------------------------------------------------------------------- settings
def test_the_model_is_registered() -> None:
    assert REGIMES["custom"] is CUSTOM
    assert CUSTOM.base_currency is None


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"gains_rate": 1.0}, "gains_rate must be a number in \\[0, 1\\)"),
        ({"income_rate": -0.1}, "income_rate"),
        ({"wealth_tax_rate": "0"}, "wealth_tax_rate"),
        ({"losses": "kept"}, "losses must be one of \\['ignored', 'netted'\\]"),
        ({"losses": "ignored"}, "loss_carry_years must be 0 when losses are ignored"),
        ({"loss_carry_years": -1}, "loss_carry_years must be an int >= 0"),
        ({"exempt_after_months": 1.5}, "exempt_after_months must be an int >= 0"),
        ({"gains_allowance": -1}, "gains_allowance must be a number >= 0"),
        ({"description": " "}, "description must be non-empty text"),
    ],
)
def test_settings_are_validated(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        CUSTOM.parse(TABLE | changes)


# --------------------------------------------------------------------------- projections
def test_the_projection_preset() -> None:
    model = custom_tax_model(CUSTOM.parse(TABLE), taxable_yield=0.02)
    assert (model.capital_gains_rate, model.wealth_tax_rate) == (0.2, 0.0)
    assert model.losses == LossRules(2, frozenset())
    assert (model.income_tax_rate, model.taxable_yield) == (0.25, 0.02)
    ignored = CUSTOM.parse(TABLE | {"losses": "ignored", "loss_carry_years": 0})
    assert custom_tax_model(ignored, taxable_yield=0.0).losses is None


def test_before_any_year_has_ended() -> None:
    """On 30 June 2025 only 2025 exists and it has not ended: no wealth tax scalar."""
    report = CUSTOM.report(_inputs(as_of=date(2025, 6, 30)), CUSTOM.parse(TABLE))
    assert "wealth_tax_estimate" not in report.scalars
    assert report.scalars["losses_remaining"] == Decimal(1000)
    with pytest.raises(ValidationError, match="custom settings expected"):
        CUSTOM.report(_inputs(), object())
