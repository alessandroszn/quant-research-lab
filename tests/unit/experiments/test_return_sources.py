"""The rule that picks each position's return series (design note 11.1), one test per row."""

from __future__ import annotations

from dataclasses import replace

import pytest

from qrlab.data.user_csv import PriceType
from qrlab.experiments.kinds._return_sources import excluded_note, return_source
from qrlab.instruments.master import Distribution, Instrument, InstrumentType
from qrlab.reporting import ReturnSource
from support.checks import A, B, C, fund

PRICE, NAV, TOTAL = PriceType.PRICE, PriceType.NAV, PriceType.TOTAL_RETURN


def _not_a_fund(kind: InstrumentType) -> Instrument:
    return replace(
        fund(A), instrument_type=kind, replication=None, distribution=None, ter=None,
        fund_size=None,
    )  # fmt: skip


def _source(instrument: Instrument | None, price_type: PriceType, **given: bool) -> ReturnSource:
    flags = {"total_return_file": False, "distributions": False} | given
    return return_source(instrument, price_type, **flags)


def test_the_first_rule_that_applies_wins() -> None:
    distributing = fund(A, distribution=Distribution.DISTRIBUTING)
    assert _source(distributing, PRICE, total_return_file=True) is ReturnSource.TOTAL_RETURN_FILE
    assert _source(distributing, PRICE, distributions=True) is ReturnSource.DISTRIBUTIONS
    assert _source(distributing, TOTAL) is ReturnSource.TOTAL_RETURN_PRICES


@pytest.mark.parametrize("price_type", [PRICE, NAV])
def test_a_fund_price_or_nav_by_its_policy(price_type: PriceType) -> None:
    assert _source(fund(A), price_type) is ReturnSource.ACCUMULATING
    distributing = fund(A, distribution=Distribution.DISTRIBUTING)
    assert _source(distributing, price_type) is ReturnSource.DISTRIBUTING
    assert _source(fund(A, distribution=None), price_type) is ReturnSource.POLICY_UNKNOWN
    assert _source(None, price_type) is ReturnSource.POLICY_UNKNOWN  # not described


def test_other_types() -> None:
    etc = fund(A, instrument_type=InstrumentType.ETC, distribution=None)
    assert _source(etc, PRICE) is ReturnSource.NO_INCOME
    assert _source(_not_a_fund(InstrumentType.STOCK), PRICE) is ReturnSource.STOCK
    assert _source(_not_a_fund(InstrumentType.BOND), PRICE) is ReturnSource.BOND
    assert _source(_not_a_fund(InstrumentType.CASH), PRICE) is ReturnSource.OTHER


def test_which_sources_include_the_income() -> None:
    included = {s for s in ReturnSource if s.income_included}
    assert included == {
        ReturnSource.TOTAL_RETURN_FILE,
        ReturnSource.DISTRIBUTIONS,
        ReturnSource.TOTAL_RETURN_PRICES,
        ReturnSource.ACCUMULATING,
        ReturnSource.NO_INCOME,
    }


def test_the_note_names_each_excluded_position_with_its_reason() -> None:
    sources = {
        C: ReturnSource.BOND,
        A: ReturnSource.DISTRIBUTING,
        B: ReturnSource.ACCUMULATING,
    }
    note = excluded_note(sources, {A: "Fund A"})
    assert note is not None
    assert f"Fund A (distributing), {C.code} (a bond):" in note  # by ISIN; the code if unnamed
    assert B.code not in note
    assert excluded_note({B: ReturnSource.ACCUMULATING}, {}) is None
