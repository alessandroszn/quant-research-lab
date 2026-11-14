"""Italian tax position (design 8.6a): every case worked by hand first.

**Five years in one amministrato account** (prices in EUR, no fees):

1. 2021: stock A bought 20 at 100, sold 20 at 50: a loss of 1,000 (balance 1,000 from 2021,
   usable until 31/12/2025).
2. 2022: ETF X bought 20 at 100, sold 20 at 200: a gain of 2,000, *redditi di capitale*: tax
   520, no offset possible.
3. 2023: ETC Y bought 10 at 100, sold 10 at 160: a gain of 600, *redditi diversi*: offset by
   600 of the 2021 losses, tax 0 (400 of 2021 left).
4. 2024: ETF Z bought 10 at 100, sold 10 at 70: a loss of 300, *redditi diversi* (balance
   +300 from 2024, usable until 31/12/2028).
5. 2026: stock B bought 10 at 100, sold 10 at 150: a gain of 500. The 400 from 2021 expired at
   the end of 2025; 300 from 2024 are used; taxable 200, tax 52.

Total tax due 572; 400 expired; nothing left.

**Public bonds (Circolare AdE 19/E of 27 June 2014).** The share of a gain or loss due to
Italian or white-list government bonds counts for 48.08 % (it is reduced by 51.92 %):

- the circular's own example: a fund gain of 300 with 26.5 % in public bonds has a base of
  300 - 79.50 x 0.5192 = 258.72 and a tax of 67.27;
- a government bond (share 100 %) with a gain of 1,000: base 480.80, tax 125.01;
- a fund with 40 % in public bonds and a loss of 1,000: 792.32 goes to the losses balance.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import Instrument, InstrumentType
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.transactions import Transaction, TransactionKind
from qrlab.tax.italy import Category, Regime, TaxPosition, italian_tax_position
from support.checks import fund
from support.lookthrough import security

EUR = Currency("EUR")
ACCOUNT = "main"
STOCK_A, STOCK_B = Isin(security("IT", 101)), Isin(security("IT", 102))
ETF_X, ETF_Z = Isin(security("IE", 103)), Isin(security("IE", 104))
ETC_Y = Isin(security("JE", 105))
BOND, BOND_FUND, US_ETF = (
    Isin(security("IT", 106)),
    Isin(security("IE", 107)),
    Isin(security("US", 108)),
)


def _instrument(isin: Isin, kind: InstrumentType, domicile: str = "IE") -> Instrument:
    base = replace(fund(isin), domicile=domicile)
    if kind in (InstrumentType.ETF, InstrumentType.FUND, InstrumentType.ETC):
        return replace(base, instrument_type=kind)
    return replace(
        base, instrument_type=kind, replication=None, distribution=None, ter=None, fund_size=None
    )


INSTRUMENTS = {
    STOCK_A: _instrument(STOCK_A, InstrumentType.STOCK, "IT"),
    STOCK_B: _instrument(STOCK_B, InstrumentType.STOCK, "IT"),
    ETF_X: _instrument(ETF_X, InstrumentType.ETF),
    ETF_Z: _instrument(ETF_Z, InstrumentType.ETF),
    ETC_Y: _instrument(ETC_Y, InstrumentType.ETC, "JE"),
    BOND: _instrument(BOND, InstrumentType.BOND, "IT"),
    BOND_FUND: _instrument(BOND_FUND, InstrumentType.ETF),
    US_ETF: _instrument(US_ETF, InstrumentType.ETF, "US"),
}
SHARES = {ETF_X: Decimal(0), ETF_Z: Decimal(0), BOND: Decimal(1), BOND_FUND: Decimal("0.4")}


class _Book:
    """Builds deposit, buy and sell transactions in EUR."""

    def __init__(self) -> None:
        self.items: list[Transaction] = []

    def _add(self, kind: TransactionKind, day: date, **fields: object) -> None:
        values: dict[str, object] = {
            "isin": None, "quantity": None, "price": None, "amount": None,
            "fees": Money.of("0", "EUR"), "taxes": Money.of("0", "EUR"), "fx_counter": None,
        }  # fmt: skip
        values.update(fields)
        self.items.append(
            Transaction(f"t{len(self.items)}", day, kind, ACCOUNT, note="", **values)  # type: ignore[arg-type]
        )

    def round_trip(
        self, isin: Isin, quantity: int, buy: str, sell: str, bought: date, sold: date,
        withheld: str = "0",
    ) -> None:  # fmt: skip
        cash = Decimal(quantity) * Decimal(buy)
        self._add(TransactionKind.DEPOSIT, bought, amount=Money(cash, EUR))
        self._add(
            TransactionKind.BUY, bought, isin=isin, quantity=Decimal(quantity),
            price=Money.of(buy, "EUR"),
        )  # fmt: skip
        self._add(
            TransactionKind.SELL, sold, isin=isin, quantity=Decimal(quantity),
            price=Money.of(sell, "EUR"), taxes=Money.of(withheld, "EUR"),
        )  # fmt: skip


def _position(
    book: _Book,
    *,
    regime: Regime = Regime.AMMINISTRATO,
    as_of: date = date(2026, 11, 14),
    shares: dict[Isin, Decimal] | None = None,
) -> TaxPosition:
    items = sorted(book.items, key=lambda t: t.trade_date)  # stable: same-day order kept
    history = replay(items, base=EUR, to_base=lambda m, d: m)
    return italian_tax_position(
        history,
        items,
        INSTRUMENTS,
        regime=regime,
        public_share=SHARES if shares is None else shares,
        as_of=as_of,
        to_base=lambda m, d: m,
    )


def _five_years() -> _Book:
    book = _Book()
    book.round_trip(STOCK_A, 20, "100", "50", date(2021, 1, 4), date(2021, 6, 1))
    book.round_trip(ETF_X, 20, "100", "200", date(2022, 1, 3), date(2022, 3, 1), withheld="520")
    book.round_trip(ETC_Y, 10, "100", "160", date(2023, 1, 2), date(2023, 5, 2))
    book.round_trip(ETF_Z, 10, "100", "70", date(2024, 1, 2), date(2024, 9, 2))
    book.round_trip(STOCK_B, 10, "100", "150", date(2026, 1, 5), date(2026, 2, 2), withheld="52")
    return book


# ------------------------------------------------------------------------------ by hand
def test_five_years_by_hand() -> None:
    position = _position(_five_years())
    events = position.events
    assert [e.category for e in events] == [
        Category.OTHER_INCOME,
        Category.CAPITAL_INCOME,
        Category.OTHER_INCOME,
        Category.OTHER_INCOME,
        Category.OTHER_INCOME,
    ]
    assert [e.gain for e in events] == [
        Decimal(-1000),
        Decimal(2000),
        Decimal(600),
        Decimal(-300),
        Decimal(500),
    ]
    assert [e.offset for e in events] == [
        Decimal(0),
        Decimal(0),
        Decimal(600),
        Decimal(0),
        Decimal(300),
    ]
    assert [e.tax_due for e in events] == [
        Decimal(0),
        Decimal("520.00"),
        Decimal(0),
        Decimal(0),
        Decimal("52.00"),
    ]
    assert position.tax_due == Decimal("572.00")
    assert position.tax_withheld == Decimal("572.00")
    assert all(e.difference == 0 for e in events)
    lots = {lot.year: lot for lot in position.losses}
    assert (lots[2021].amount, lots[2021].used, lots[2021].expired) == (
        Decimal(1000),
        Decimal(600),
        Decimal(400),
    )
    assert lots[2021].expires == date(2025, 12, 31)
    assert (lots[2024].amount, lots[2024].used, lots[2024].remaining) == (
        Decimal(300),
        Decimal(300),
        Decimal(0),
    )
    assert lots[2024].expires == date(2028, 12, 31)
    assert position.losses_remaining == 0


def test_the_balance_before_the_expiry() -> None:
    """On 30/06/2025 the 400 from 2021 are still usable."""
    book = _five_years()
    book.items = [t for t in book.items if t.trade_date < date(2025, 1, 1)]
    position = _position(book, as_of=date(2025, 6, 30))
    assert position.losses_remaining == Decimal(700)  # 400 from 2021 + 300 from 2024


def test_the_circulars_example_and_government_bonds() -> None:
    book = _Book()
    book.round_trip(BOND_FUND, 10, "100", "130", date(2025, 1, 2), date(2025, 3, 3))
    shares = dict(SHARES) | {BOND_FUND: Decimal("0.265")}
    event = _position(book, shares=shares).events[0]
    assert event.gain == Decimal(300)
    assert event.base == Decimal("258.7236")  # 300 - 79.50 x 0.5192
    assert event.tax_due == Decimal("67.27")
    book = _Book()
    book.round_trip(BOND, 10, "100", "200", date(2025, 1, 2), date(2025, 3, 3))
    event = _position(book).events[0]
    assert event.base == Decimal("480.80")
    assert event.tax_due == Decimal("125.01")


def test_a_fund_loss_with_public_bonds_enters_the_balance_reduced() -> None:
    book = _Book()
    book.round_trip(BOND_FUND, 10, "200", "100", date(2025, 1, 2), date(2025, 3, 3))
    position = _position(book)
    assert position.events[0].category is Category.OTHER_INCOME  # a fund loss is redditi diversi
    assert position.losses[0].amount == Decimal("792.32")  # 1,000 x (0.6 + 0.4 x 0.4808)


def test_dichiarativo_nets_within_the_year() -> None:
    """A gain of 500 in February and a loss of 300 in October of the same year.

    Amministrato: the gain is taxed when realised (130) and the loss goes to the balance.
    Dichiarativo: the year's net 200 is taxed (52) and nothing is carried.
    """
    book = _Book()
    book.round_trip(STOCK_A, 10, "100", "150", date(2025, 1, 2), date(2025, 2, 3))
    book.round_trip(STOCK_B, 10, "100", "70", date(2025, 1, 2), date(2025, 10, 1))
    amministrato = _position(book)
    assert amministrato.tax_due == Decimal("130.00")
    assert amministrato.losses_remaining == Decimal(300)
    dichiarativo = _position(book, regime=Regime.DICHIARATIVO)
    assert dichiarativo.tax_due == Decimal("52.00")
    assert dichiarativo.losses_remaining == 0
    assert all(e.tax_withheld == 0 for e in dichiarativo.events)


def test_the_tax_withheld_is_added_back_to_the_gain() -> None:
    """The ledger's gain is net of every charge on the sale; the taxable gain is not net of tax."""
    book = _Book()
    book.round_trip(ETF_X, 20, "100", "200", date(2022, 1, 3), date(2022, 3, 1), withheld="520")
    history = replay(book.items, base=EUR, to_base=lambda m, d: m)
    assert history.realised[0].gain_base == Decimal(2000 - 520)
    assert _position(book).events[0].gain == Decimal(2000)


def test_a_wrong_withholding_is_shown_not_absorbed() -> None:
    book = _Book()
    book.round_trip(ETF_X, 20, "100", "200", date(2022, 1, 3), date(2022, 3, 1), withheld="500")
    event = _position(book).events[0]
    assert (event.tax_due, event.tax_withheld, event.difference) == (
        Decimal("520.00"),
        Decimal("500.00"),
        Decimal("-20.00"),
    )


# ------------------------------------------------------------------------------ flags, errors
def test_a_non_harmonised_fund_is_flagged_not_computed() -> None:
    book = _Book()
    book.round_trip(US_ETF, 10, "100", "150", date(2025, 1, 2), date(2025, 3, 3))
    position = _position(book, shares=dict(SHARES) | {US_ETF: Decimal(0)})
    assert position.events[0].category is Category.NOT_COMPUTED
    assert position.events[0].tax_due is None
    assert position.flagged == (US_ETF.code,)
    assert position.tax_due == 0


def test_a_fund_without_its_public_share_raises() -> None:
    book = _Book()
    book.round_trip(BOND_FUND, 10, "100", "130", date(2025, 1, 2), date(2025, 3, 3))
    with pytest.raises(ValidationError, match="public"):
        _position(book, shares={})


@pytest.mark.parametrize("sold", [date(2014, 6, 30), date(2028, 1, 3)])
def test_sales_outside_the_checked_rules_raise(sold: date) -> None:
    book = _Book()
    book.round_trip(STOCK_A, 10, "100", "150", date(2014, 1, 2), sold)
    with pytest.raises(ValidationError, match="rules"):
        _position(book, as_of=date(2028, 6, 30))


def test_an_instrument_without_master_data_raises() -> None:
    book = _Book()
    other = Isin(security("IT", 109))
    book.round_trip(other, 10, "100", "150", date(2025, 1, 2), date(2025, 3, 3))
    with pytest.raises(ValidationError, match="instruments"):
        _position(book)


def test_sources_are_stated() -> None:
    sources = " ".join(_position(_five_years()).sources)
    for text in ("917/1986", "117/2026", "19/E", "461/1997", "111/2023"):
        assert text in sources


def test_dichiarativo_net_loss_and_capital_income() -> None:
    """A loss of 300 and a gain of 100 on shares in one year: a net loss of 200 is carried.

    The ETF gain of 1,000 in the same year is capital income: 260, whatever the losses.
    """
    book = _Book()
    book.round_trip(STOCK_A, 10, "100", "70", date(2025, 1, 2), date(2025, 2, 3))
    book.round_trip(STOCK_B, 10, "100", "110", date(2025, 1, 2), date(2025, 6, 2))
    book.round_trip(ETF_X, 10, "100", "200", date(2025, 1, 2), date(2025, 9, 1))
    position = _position(book, regime=Regime.DICHIARATIVO)
    assert position.tax_due == Decimal("260.00")
    assert position.losses_remaining == Decimal(200)


def test_dichiarativo_tax_adds_up_over_several_gains() -> None:
    """Three gains of 100 each, no losses: 3 x 26 = 78 exactly, spread to the cent."""
    book = _Book()
    for isin in (STOCK_A, STOCK_B, ETC_Y):
        book.round_trip(isin, 1, "100", "200", date(2025, 1, 2), date(2025, 3, 3))
    position = _position(book, regime=Regime.DICHIARATIVO)
    assert [e.tax_due for e in position.events] == [Decimal("26.00")] * 3
    assert position.tax_due == Decimal("78.00")


def test_dichiarativo_year_that_nets_to_zero() -> None:
    book = _Book()
    book.round_trip(STOCK_A, 10, "100", "130", date(2025, 1, 2), date(2025, 2, 3))
    book.round_trip(STOCK_B, 10, "100", "70", date(2025, 1, 2), date(2025, 6, 2))
    position = _position(book, regime=Regime.DICHIARATIVO)
    assert position.tax_due == 0
    assert position.losses == ()


def test_bad_regime_and_share_raise() -> None:
    book = _Book()
    book.round_trip(ETF_X, 10, "100", "130", date(2025, 1, 2), date(2025, 2, 3))
    with pytest.raises(ValidationError, match="regime"):
        _position(book, regime="amministrato")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match=r"\[0, 1\]"):
        _position(book, shares={ETF_X: Decimal("1.5")})
