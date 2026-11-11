"""Instrument master data: validation, and explicit reports of missing or stale fields.

All instruments here are synthetic; ISINs are valid codes used only as identifiers.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import (
    AssetClass,
    Distribution,
    Instrument,
    InstrumentType,
    Issue,
    IssueKind,
    Replication,
    master_data_issues,
)

ON = date(2026, 11, 10)


def _etf(**changes: object) -> Instrument:
    base = Instrument(
        isin=Isin("IE00B4L5Y983"),
        name="Example World Equity UCITS ETF",
        instrument_type=InstrumentType.ETF,
        asset_class=AssetClass.EQUITY,
        currency=Currency("USD"),
        as_of=date(2026, 10, 1),
        domicile="IE",
        replication=Replication.PHYSICAL_SAMPLING,
        distribution=Distribution.ACCUMULATING,
        ter=Decimal("0.0020"),
        benchmark="Example World Index",
        hedged_to=None,
        inception=date(2009, 9, 25),
        fund_size=Money.of("85000000000", "USD"),
        source="synthetic test record",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def _stock(**changes: object) -> Instrument:
    defaults: dict[str, object] = {
        "isin": Isin("US0378331005"),
        "name": "Example Stock",
        "instrument_type": InstrumentType.STOCK,
        "replication": None,
        "distribution": None,
        "ter": None,
        "benchmark": None,
        "fund_size": None,
        "domicile": "US",
    }
    return _etf(**(defaults | changes))


# --------------------------------------------------------------------------- validation
def test_valid_records() -> None:
    assert _etf().ter == Decimal("0.0020")
    assert _stock().replication is None


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"ter": Decimal("0.2")}, "TER"),  # 0.20 % entered as 0.2: caught by the range check
        ({"ter": Decimal("-0.001")}, "TER"),
        ({"ter": 0.002}, "Decimal"),
        ({"ter": Decimal("NaN")}, "TER"),
        ({"name": "  "}, "name"),
        ({"name": " padded "}, "name"),
        ({"hedged_to": Currency("USD")}, "hedged_to"),
        ({"as_of": date(2009, 1, 1)}, "inception"),
        ({"as_of": datetime(2026, 10, 1, 12, 0)}, "date"),
        ({"domicile": "XX"}, "country"),
        ({"source": ""}, "source"),
        ({"benchmark": ""}, "benchmark"),
        ({"instrument_type": "etf"}, "InstrumentType"),
        ({"currency": "USD"}, "Currency"),
    ],
)
def test_invalid_records_raise(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _etf(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"replication": Replication.PHYSICAL_FULL},
        {"distribution": Distribution.DISTRIBUTING},
        {"ter": Decimal("0.001")},
    ],
)
def test_fund_only_fields_on_a_stock_raise(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="fund"):
        _stock(**changes)


def test_ter_upper_bound_is_inclusive() -> None:
    assert _etf(ter=Decimal("0.03")).ter == Decimal("0.03")
    with pytest.raises(ValidationError, match="TER"):
        _etf(ter=Decimal("0.0301"))


def test_ter_percent_property() -> None:
    assert _etf().ter_percent == Decimal("0.20")
    assert _etf(ter=None).ter_percent is None


# --------------------------------------------------------------------------- issues
def test_complete_fresh_record_has_no_issues() -> None:
    assert master_data_issues([_etf(), _stock()], on=ON, max_age_days=365) == []


def test_missing_fund_fields_are_reported_not_filled() -> None:
    record = _etf(
        domicile=None, replication=None, distribution=None, ter=None, benchmark=None, fund_size=None
    )
    issues = master_data_issues([record], on=ON, max_age_days=365)
    assert {(i.field, i.kind) for i in issues} == {
        ("domicile", IssueKind.MISSING),
        ("replication", IssueKind.MISSING),
        ("distribution", IssueKind.MISSING),
        ("ter", IssueKind.MISSING),
        ("benchmark", IssueKind.MISSING),
        ("fund_size", IssueKind.MISSING),
    }
    assert all(i.subject == "IE00B4L5Y983" for i in issues)


def test_stock_without_fund_fields_has_no_missing_issues() -> None:
    assert master_data_issues([_stock(domicile=None)], on=ON, max_age_days=365) == [
        Issue("US0378331005", "domicile", IssueKind.MISSING, "domicile is unknown")
    ]


def test_staleness_uses_the_callers_threshold() -> None:
    record = _etf(as_of=date(2026, 1, 1))  # 313 days before ON
    assert master_data_issues([record], on=ON, max_age_days=313) == []
    issues = master_data_issues([record], on=ON, max_age_days=312)
    assert [(i.field, i.kind) for i in issues] == [("as_of", IssueKind.STALE)]
    assert "313 days" in issues[0].detail


def test_future_as_of_is_reported() -> None:
    issues = master_data_issues([_etf(as_of=date(2026, 12, 1))], on=ON, max_age_days=365)
    assert [(i.field, i.kind) for i in issues] == [("as_of", IssueKind.FUTURE)]


def test_duplicated_isins_are_reported() -> None:
    issues = master_data_issues([_etf(), _etf(name="Other name")], on=ON, max_age_days=365)
    assert [(i.field, i.kind) for i in issues] == [("isin", IssueKind.DUPLICATE)]


@pytest.mark.parametrize("bad", [-1, 1.5, True])
def test_max_age_days_must_be_non_negative_int(bad: object) -> None:
    with pytest.raises(ValidationError, match="max_age_days"):
        master_data_issues([_etf()], on=ON, max_age_days=bad)  # type: ignore[arg-type]


def test_hedged_share_class_and_unknown_inception_are_valid() -> None:
    record = _etf(hedged_to=Currency("EUR"), inception=None)
    assert record.hedged_to == Currency("EUR")
    assert record.inception is None


def test_fund_size_validation() -> None:
    with pytest.raises(ValidationError, match="fund_size"):
        _etf(fund_size=Money.of(0, "USD"))
    with pytest.raises(ValidationError, match="fund_size"):
        _etf(fund_size=1_000_000)
    with pytest.raises(ValidationError, match="fund"):
        _stock(fund_size=Money.of(1, "USD"))
