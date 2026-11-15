"""Swiss tax analytics of a private investor (design 9.2), by hand. All data synthetic, CHF.

The account: fund A (Irish, accumulating, ISIN IE0000000012) and fund B (Swiss, distributing,
CH0000000023); marginal income rate 30 %, wealth-tax rate 3 per mille.

- **2025.** Deposit 100,000; buy 400 A and 500 B at 100 on 1 December. Cash 10,000. On 31
  December the account is worth 100,000: the wealth tax is 300. Purchases 90,000 are below
  5 x 100,000 (the first year starts from its first valuation). Without a net income the
  gains criterion is "not checked", so the year is incomplete.
- **2026.**
  - 1 Feb: deposit 100,000 and buy 1,000 B at 100.
  - 15 Mar: B pays a dividend of 1,200 gross, with 420 Swiss withholding tax (35 %),
    refundable.
  - 1 Jun: sell 1,000 B at 130. First in, first out, the units are the 500 of 1 Dec 2025
    (exactly 6 months) and 500 of 1 Feb 2026 (4 months): the holding period is not met. Under
    average cost (100) the gain is 30,000.
  - 30 Jun: A's yearly closing; the price list gives 2.50 per unit, and 400 units are held,
    so 1,000 of income.
  - 1 Jul: buy 1,000 A at 100. 1 Sep: sell 200 A at 100 (no gain).
  - Volume: purchases 200,000 + sales 150,000 = 350,000 <= 5 x 100,000.
  - Gains 30,000 < 50 % of the net income of 80,000.
  - Income 1,200 + 1,000 = 2,200, taxed at 30 %: 660.
  - Cash at year end 60,780; A 1,200 units at 100 and B 500 at 130: wealth 245,780, tax
    737.34.
  - Professional trading cannot be excluded (the holding period is not met).
- **2027.** 1 Feb: sell 100 A at 110. The oldest A units date from 1 Dec 2025 (14 months):
  met. The gain is 1,000, below 50 % of 60,000; the volume is 11,000. All five criteria
  are met: private wealth management.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.master import Distribution, Instrument
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.transactions import TransactionKind
from qrlab.portfolio.valuation import value_portfolio
from qrlab.tax import REGIMES, TaxInputs, TaxReport, TaxTable
from qrlab.tax.switzerland import SWITZERLAND, add_months, shortest_holdings
from support.portfolio import price_series, tx
from support.report import toy_instrument
from support.swiss import CHF, TRANSACTIONS, A, B, chf, trade

K = TransactionKind


def same(amount: Money, on: date) -> Money:
    assert amount.currency == CHF, amount
    return amount


JUNE_30 = date(2026, 6, 30)
TABLE = {
    "marginal_rate": 0.30,
    "wealth_tax_rate": 0.003,
    "net_income": {"2026": 80000, "2027": 60000},
    "debt_financed": False,
    "reported_income": {
        A.code: [{"date": date(2026, 6, 30), "per_unit": "2.50", "currency": "CHF"}]
    },
}


def _inputs(
    transactions: list | None = None,  # type: ignore[type-arg]
    as_of: date = date(2027, 3, 31),
    days: list[date] | None = None,
) -> TaxInputs:
    rows = TRANSACTIONS if transactions is None else transactions
    history = replay(rows, base=CHF, to_base=same)
    days = days or [date(2025, 12, 31), date(2026, 12, 31), as_of]
    prices = {
        A: price_series({d: 100.0 if d.year < 2027 else 110.0 for d in days}, CHF),
        B: price_series({d: 100.0 if d.year < 2026 else 130.0 for d in days}, CHF),
    }
    valuation = value_portfolio(history, prices, same, dates=days, max_price_age_days=0)
    fund = toy_instrument()
    instruments = {
        A: Instrument(**{**fund.__dict__, "isin": A, "currency": CHF}),
        B: Instrument(
            **{
                **fund.__dict__,
                "isin": B,
                "currency": CHF,
                "domicile": "CH",
                "distribution": Distribution.DISTRIBUTING,
                "name": "Example Swiss Fund",
            }
        ),
    }
    return TaxInputs(history, rows, instruments, valuation, same, as_of)


def _report(**changes: object) -> TaxReport:
    return SWITZERLAND.report(_inputs(), SWITZERLAND.parse(TABLE | changes))


def _table(report: TaxReport, file: str) -> TaxTable:
    return next(t for t in report.tables if t.file == file)


def _rows(report: TaxReport, file: str) -> list[dict[str, object]]:
    table = _table(report, file)
    return [dict(zip((c.key for c in table.columns), row, strict=True)) for row in table.rows]


# --------------------------------------------------------------------------- the years
def test_the_years_by_hand() -> None:
    years = {r["year"]: r for r in _rows(_report(), "ch_years")}
    assert list(years) == [2025, 2026, 2027]
    assert years[2025]["wealth"] == Decimal(100000)
    assert years[2025]["wealth_tax"] == Decimal("300.00")
    y = years[2026]
    assert (y["gains"], y["income"], y["income_tax"]) == (30000, 2200, Decimal("660.00"))
    assert (y["wealth"], y["wealth_tax"]) == (Decimal(245780), Decimal("737.34"))
    assert (y["withholding_refundable"], y["safe_haven"]) == (420, "not_excluded")
    assert years[2027]["wealth"] is None  # the year has not ended on 31 March 2027
    assert years[2027]["gains"] == 1000
    assert years[2027]["safe_haven"] == "met"
    assert years[2025]["safe_haven"] == "incomplete"


def test_the_scalars_are_for_the_latest_complete_year() -> None:
    assert _report().scalars == {
        "gains_realised": Decimal(30000),
        "safe_haven_met": Decimal(0),
        "income_taxable": Decimal(2200),
        "income_tax_estimate": Decimal("660.00"),
        "withholding_refundable": Decimal(420),
        "wealth": Decimal(245780),
        "wealth_tax_estimate": Decimal("737.34"),
    }


def test_the_income_items() -> None:
    items = _rows(_report(), "ch_income")
    assert [(i["date"], i["isin"], i["kind"]) for i in items] == [
        (date(2026, 3, 15), B.code, "dividend"),
        (date(2026, 6, 30), A.code, "reported_income"),
    ]
    assert (items[0]["gross"], items[0]["withheld"], items[0]["refundable"]) == (1200, 420, 420)
    assert (items[1]["gross"], items[1]["units"], items[1]["per_unit"]) == (
        1000,
        400,
        Decimal("2.50"),
    )


# --------------------------------------------------------------------------- Circular 36
def test_the_safe_haven_check_by_hand() -> None:
    rows = _rows(_report(), "ch_safe_haven")
    year = {(r["year"], r["criterion"]): r for r in rows}
    holding = year[(2026, "holding")]
    assert holding["result"] == "not_met"
    assert holding["detail"] == "2026-02-01 → 2026-06-01"
    volume = year[(2026, "volume")]
    assert (volume["value"], volume["limit"], volume["result"]) == (350000, 500000, "met")
    gains = year[(2026, "gains")]
    assert (gains["value"], gains["limit"], gains["result"]) == (30000, 40000, "met")
    assert year[(2026, "debt")]["result"] == "met"
    assert year[(2026, "derivatives")]["result"] == "met"
    assert year[(2027, "holding")]["detail"] == "2025-12-01 → 2027-02-01"
    assert all(year[(2027, c)]["result"] == "met" for c in ("holding", "volume", "gains"))
    assert year[(2025, "gains")]["result"] == "not_checked"
    assert year[(2025, "holding")]["detail"] == ""  # no sale in 2025
    assert year[(2025, "volume")]["limit"] == 500000  # from the first valuation, noted


def test_debt_financing_cannot_be_checked_by_qrlab() -> None:
    rows = _rows(_report(debt_financed=True), "ch_safe_haven")
    assert {r["result"] for r in rows if r["criterion"] == "debt"} == {"not_checked"}


def test_shortest_holding_is_first_in_first_out() -> None:
    """100 units in January, 100 in August, 150 sold the next March: 14 and 7 months."""
    rows = [
        trade("d", date(2026, 1, 10), K.DEPOSIT, amount=chf(1000)),
        trade("b1", date(2026, 1, 10), K.BUY, isin=A, quantity="100", price=chf(1)),
        trade("b2", date(2026, 8, 10), K.BUY, isin=A, quantity="100", price=chf(1)),
        trade("s", date(2027, 3, 10), K.SELL, isin=A, quantity="150", price=chf(1)),
    ]  # fmt: skip
    (sale,) = shortest_holdings(rows)
    assert (sale.sold, sale.acquired) == (date(2027, 3, 10), date(2026, 8, 10))
    assert sale.sold >= add_months(sale.acquired, 6)


def test_months_are_calendar_months() -> None:
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert add_months(date(2027, 8, 31), 6) == date(2028, 2, 29)
    assert add_months(date(2026, 12, 1), 6) == date(2027, 6, 1)


# --------------------------------------------------------------------------- settings
def test_the_regime_is_registered() -> None:
    assert REGIMES["ch"] is SWITZERLAND
    assert SWITZERLAND.keys == frozenset(
        {"marginal_rate", "wealth_tax_rate", "net_income", "debt_financed", "reported_income"}
    )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"marginal_rate": 1.0}, "marginal_rate must be a number in \\[0, 1\\)"),
        ({"wealth_tax_rate": -0.1}, "wealth_tax_rate must be a number in \\[0, 1\\)"),
        ({"net_income": {"twenty": 1}}, "net_income: 'twenty' is not a year"),
        ({"net_income": {"2026": -5}}, "net_income of 2026 must be a number >= 0"),
        ({"debt_financed": "no"}, "debt_financed must be true or false"),
        ({"reported_income": {A.code: [{"date": JUNE_30, "per_unit": "2.5"}]}}, "currency"),
        (
            {"reported_income": {A.code: [{"date": JUNE_30, "per_unit": 2.5, "currency": "CHF"}]}},
            "quoted decimal",
        ),
        ({"reported_income": {A.code: {"date": 1}}}, "a list of"),
    ],
)  # fmt: skip
def test_settings_are_validated(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        SWITZERLAND.parse(TABLE | changes)


def test_inputs_are_checked() -> None:
    eur = replay(
        [tx("d", date(2026, 1, 2), K.DEPOSIT, amount=Money.of(1, "EUR"))],
        base=Currency("EUR"),
        to_base=lambda m, d: m,
    )
    inputs = TaxInputs(eur, (), {}, _inputs().valuation, same, date(2027, 3, 31))
    with pytest.raises(ValidationError, match='base_currency = "CHF"'):
        SWITZERLAND.report(inputs, SWITZERLAND.parse(TABLE))
    late = TABLE | {
        "reported_income": {
            A.code: [{"date": date(2025, 6, 30), "per_unit": "1", "currency": "CHF"}]
        }
    }
    with pytest.raises(ValidationError, match="no units of IE0000000012 are held on 2025-06-30"):
        SWITZERLAND.report(_inputs(), SWITZERLAND.parse(late))
    with pytest.raises(ValidationError, match="Swiss settings expected"):
        SWITZERLAND.report(_inputs(), object())


# --------------------------------------------------------------------------- edges
def test_splits_and_transfers_out_in_the_holding_period() -> None:
    """A 2-for-1 split doubles the January lot; 150 units leave by transfer, then 100 are sold.

    The transfer takes 150 of the 200 January units; the sale takes the other 50 and 50 of
    August's, so its latest acquisition is August. A transfer out is not a sale.
    """
    rows = [
        trade("d", date(2026, 1, 10), K.DEPOSIT, amount=chf(1000)),
        trade("b1", date(2026, 1, 10), K.BUY, isin=A, quantity="100", price=chf(1)),
        trade("x", date(2026, 3, 1), K.SPLIT, isin=A, quantity="2"),
        trade("b2", date(2026, 8, 10), K.BUY, isin=A, quantity="100", price=chf(1)),
        trade("o", date(2026, 9, 1), K.TRANSFER_OUT, isin=A, quantity="150", price=chf(1)),
        trade("s", date(2027, 3, 10), K.SELL, isin=A, quantity="100", price=chf(1)),
    ]
    (sale,) = shortest_holdings(rows)
    assert (sale.sold, sale.acquired) == (date(2027, 3, 10), date(2026, 8, 10))


def test_income_after_the_report_date_is_left_out() -> None:
    inputs = _inputs(as_of=date(2026, 3, 1), days=[date(2025, 12, 31), date(2026, 3, 1)])
    report = SWITZERLAND.report(inputs, SWITZERLAND.parse(TABLE))
    assert _rows(report, "ch_income") == []
    assert report.scalars["wealth"] == Decimal(100000)  # 2025, the latest complete year


def test_before_any_complete_year_there_is_no_wealth_scalar() -> None:
    days = [date(2025, 12, 1), date(2025, 12, 15)]
    report = SWITZERLAND.report(
        _inputs(as_of=date(2025, 12, 15), days=days), SWITZERLAND.parse(TABLE)
    )
    assert "wealth" not in report.scalars
    assert report.scalars["income_taxable"] == 0


def test_a_year_without_any_valuation_cannot_check_the_volume() -> None:
    days = [date(2026, 12, 31), date(2027, 3, 31)]
    report = SWITZERLAND.report(_inputs(days=days), SWITZERLAND.parse(TABLE))
    volume = {r["year"]: r for r in _rows(report, "ch_safe_haven") if r["criterion"] == "volume"}
    assert (volume[2025]["limit"], volume[2025]["result"]) == (None, "not_checked")


def test_with_a_valuation_before_the_first_year_there_is_no_first_year_note() -> None:
    """A valuation on 31/12/2024, before any transaction, starts 2025 from 0."""
    days = [date(2024, 12, 31), date(2025, 12, 31), date(2026, 12, 31), date(2027, 3, 31)]
    report = SWITZERLAND.report(_inputs(days=days), SWITZERLAND.parse(TABLE))
    assert "ch_first_year" not in [p.key for p in report.paragraphs]
    volume = {r["year"]: r for r in _rows(report, "ch_safe_haven") if r["criterion"] == "volume"}
    assert (volume[2025]["limit"], volume[2025]["result"]) == (0, "not_met")


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"net_income": [1]}, "net_income must be a table"),
        ({"reported_income": [1]}, "reported_income must be a table"),
        (
            {"reported_income": {A.code: [{"date": "x", "per_unit": "1", "currency": "CHF"}]}},
            "date must be a TOML date",
        ),
        (
            {"reported_income": {A.code: [{"date": JUNE_30, "per_unit": "a", "currency": "CHF"}]}},
            "is not a decimal",
        ),
        (
            {"reported_income": {A.code: [{"date": JUNE_30, "per_unit": "-1", "currency": "CHF"}]}},
            "must be >= 0",
        ),
    ],
)  # fmt: skip
def test_more_settings_are_validated(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        SWITZERLAND.parse(TABLE | changes)
