"""Look-through exposures and overlap. All holdings synthetic.

Hand values (design note 2.5):

- fund A at 60 % (US 0.6, JP 0.4), fund B at 30 % (US 0.5, DE 0.5), cash 10 %:
  US 0.36 + 0.15 = 0.51, JP 0.24, DE 0.15, cash 0.10, total 1;
- holdings summing to 0.98 in a fund at 0.5: unexplained 0.5 x 0.02 = 0.01 as reported, 0 when
  normalised;
- a holding without country at 0.1 of a fund at 0.5: unknown 0.05;
- f = {X 0.5, Y 0.3, Z 0.2}, g = {X 0.4, Y 0.4, W 0.2}: overlap 0.4 + 0.3 = 0.70; each fund at
  0.5 of the portfolio duplicates X 0.25 + 0.20 and Y 0.15 + 0.20 = 0.80.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.instruments.holdings import HoldingsSnapshot
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import Instrument, InstrumentType
from qrlab.lookthrough import (
    CASH,
    NOT_LOOKED_THROUGH,
    UNEXPLAINED,
    UNKNOWN,
    Dimension,
    LookThrough,
    WeightTreatment,
    duplicated_exposure,
    look_through,
    pair_overlap,
    pairwise_overlaps,
)
from support.checks import AS_OF, A, B, C, D, fund
from support.lookthrough import W, X, Y, Z, countries, holding, security, snapshot

EUR, USD = Currency("EUR"), Currency("USD")
AS_REPORTED = WeightTreatment.AS_REPORTED


def _look(
    weights: Mapping[Isin, float],
    snapshots: Mapping[Isin, HoldingsSnapshot],
    *,
    cash: Mapping[Currency, float] | None = None,
    instruments: Mapping[Isin, Instrument] | None = None,
    treatment: WeightTreatment = AS_REPORTED,
    issuers: Mapping[Isin, str] | None = None,
) -> LookThrough:
    return look_through(
        as_of=AS_OF,
        position_weights=weights,
        cash_weights=cash or {},
        instruments=instruments if instruments is not None else {i: fund(i) for i in weights},
        snapshots=snapshots,
        treatment=treatment,
        issuers=issuers,
    )


def _largest(lt: LookThrough, dimension: Dimension) -> tuple[str, object]:
    found = lt.largest(dimension)
    assert found is not None
    return found


# --------------------------------------------------------------------------- exposures
def test_country_exposure_hand_example() -> None:
    lt = _look(
        {A: 0.6, B: 0.3},
        {A: countries(A, {"US": 0.6, "JP": 0.4}), B: countries(B, {"US": 0.5, "DE": 0.5})},
        cash={EUR: 0.1},
    )
    exposure = lt.exposure(Dimension.COUNTRY)
    assert list(exposure.index) == ["US", "JP", "DE", CASH]
    assert exposure.to_list() == pytest.approx([0.51, 0.24, 0.15, 0.10])
    assert float(exposure.sum()) == pytest.approx(1.0)
    assert _largest(lt, Dimension.COUNTRY) == ("US", pytest.approx(0.51))
    assert lt.exposure(Dimension.CURRENCY).to_dict() == pytest.approx({"USD": 0.9, "EUR": 0.1})
    assert lt.snapshot_dates == {A: date(2026, 5, 31), B: date(2026, 5, 31)}
    assert lt.bucket(Dimension.COUNTRY, "FR") == 0.0


def test_unexplained_weight_as_reported_and_normalised() -> None:
    holdings = {A: countries(A, {"US": 0.60, "JP": 0.38})}
    reported = _look({A: 0.5}, holdings, cash={EUR: 0.5})
    assert reported.bucket(Dimension.COUNTRY, UNEXPLAINED) == pytest.approx(0.01)
    assert reported.bucket(Dimension.SECTOR, UNEXPLAINED) == pytest.approx(0.01)
    normalised = _look({A: 0.5}, holdings, cash={EUR: 0.5}, treatment=WeightTreatment.NORMALISED)
    assert normalised.bucket(Dimension.COUNTRY, UNEXPLAINED) == 0.0
    assert normalised.bucket(Dimension.COUNTRY, "US") == pytest.approx(0.5 * 0.60 / 0.98)


def test_unknown_fields_are_never_assigned() -> None:
    rows = [
        holding("Known", 0.9, isin=X, country="US", sector="Tech", currency="USD"),
        holding("Mystery", 0.1),
    ]
    lt = _look({A: 0.5}, {A: snapshot(A, rows)}, cash={EUR: 0.5})
    assert lt.bucket(Dimension.COUNTRY, UNKNOWN) == pytest.approx(0.05)
    assert lt.bucket(Dimension.SECTOR, UNKNOWN) == pytest.approx(0.05)
    assert lt.bucket(Dimension.CURRENCY, UNKNOWN) == pytest.approx(0.05)
    assert lt.bucket(Dimension.SECURITY, "name:Mystery") == pytest.approx(0.05)


def test_direct_positions_and_funds_without_holdings() -> None:
    stock = fund(C, instrument_type=InstrumentType.STOCK, ter=None, replication=None,
                 distribution=None, benchmark=None, fund_size=None, domicile="NL",
                 currency=EUR)  # fmt: skip
    lt = _look(
        {A: 0.4, B: 0.3, C: 0.2, D: 0.1},
        {A: countries(A, {"US": 1.0})},
        instruments={A: fund(A), B: fund(B), C: stock},  # D has no master data
    )
    country = lt.exposure(Dimension.COUNTRY)
    assert country.to_dict() == pytest.approx({"US": 0.4, NOT_LOOKED_THROUGH: 0.4, "NL": 0.2})
    assert lt.bucket(Dimension.SECURITY, C.code) == pytest.approx(0.2)
    assert lt.bucket(Dimension.SECTOR, UNKNOWN) == pytest.approx(0.6)  # A has no sectors
    assert set(lt.snapshot_dates) == {A}


def test_only_cash_and_special_buckets_have_no_largest() -> None:
    lt = _look({A: 0.5}, {}, cash={EUR: 0.5})
    assert lt.largest(Dimension.COUNTRY) is None
    assert lt.exposure(Dimension.COUNTRY).to_dict() == pytest.approx(
        {NOT_LOOKED_THROUGH: 0.5, CASH: 0.5}
    )
    assert lt.exposure(Dimension.CURRENCY).to_dict() == pytest.approx(
        {NOT_LOOKED_THROUGH: 0.5, "EUR": 0.5}
    )


def test_hedged_share_class_keeps_underlying_currencies() -> None:
    lt = _look(
        {A: 1.0},
        {A: countries(A, {"US": 0.7, "JP": 0.3})},
        instruments={A: fund(A, currency=USD, hedged_to=EUR)},
    )
    assert lt.exposure(Dimension.CURRENCY).to_dict() == pytest.approx({"EUR": 1.0})
    assert lt.exposure(Dimension.UNDERLYING_CURRENCY).to_dict() == pytest.approx({"USD": 1.0})


def test_issuers_group_securities_only_with_a_map() -> None:
    rows = [
        holding("Alpha class A", 0.3, isin=X, country="US"),
        holding("Alpha class C", 0.3, isin=Y, country="US"),
        holding("Beta", 0.4, isin=Z, country="US"),
    ]
    without = _look({A: 1.0}, {A: snapshot(A, rows)})
    assert without.issuer_mapped is False
    assert _largest(without, Dimension.ISSUER) == (Z, pytest.approx(0.4))
    mapped = _look({A: 1.0}, {A: snapshot(A, rows)}, issuers={Isin(X): "Alpha", Isin(Y): "Alpha"})
    assert mapped.issuer_mapped is True
    assert _largest(mapped, Dimension.ISSUER) == ("Alpha", pytest.approx(0.6))


def test_ties_are_ordered_by_name() -> None:
    lt = _look({A: 1.0}, {A: countries(A, {"US": 0.5, "DE": 0.5})})
    assert list(lt.exposure(Dimension.COUNTRY).index) == ["DE", "US"]


def test_snapshot_checks() -> None:
    with pytest.raises(ValidationError, match="stored under"):
        _look({A: 1.0}, {A: countries(B, {"US": 1.0})})
    late = snapshot(A, [holding("X", 1.0, isin=X)], as_of=date(2026, 7, 1))
    with pytest.raises(ValidationError, match="after"):
        _look({A: 1.0}, {A: late})
    ignored = _look({A: 1.0}, {A: countries(A, {"US": 1.0}), B: countries(B, {"DE": 1.0})})
    assert set(ignored.snapshot_dates) == {A}


def test_weights_above_one_are_shown_not_capped() -> None:
    lt = _look({A: 1.0}, {A: countries(A, {"US": 1.1})})
    assert lt.bucket(Dimension.COUNTRY, "US") == pytest.approx(1.1)
    assert lt.bucket(Dimension.COUNTRY, UNEXPLAINED) == pytest.approx(-0.1)


# --------------------------------------------------------------------------- overlap
F_ROWS = [holding("X", 0.5, isin=X), holding("Y", 0.3, isin=Y), holding("Z", 0.2, isin=Z)]
G_ROWS = [holding("X", 0.4, isin=X), holding("Y", 0.4, isin=Y), holding("W", 0.2, isin=W)]


def test_pair_overlap_hand_example() -> None:
    result = pair_overlap(snapshot(A, F_ROWS), snapshot(B, G_ROWS), treatment=AS_REPORTED)
    assert result.overlap == pytest.approx(0.70)
    assert (result.first, result.second) == (A, B)
    assert (result.unmatched_first, result.unmatched_second) == (0.0, 0.0)


def test_identical_and_disjoint_funds() -> None:
    f = snapshot(A, F_ROWS)
    assert pair_overlap(f, snapshot(B, F_ROWS), treatment=AS_REPORTED).overlap == pytest.approx(1)
    other = snapshot(B, [holding("Q", 1.0, isin=security("DE", 9))])
    assert pair_overlap(f, other, treatment=AS_REPORTED).overlap == 0.0


def test_overlap_sums_duplicates_ignores_shorts_and_reports_unmatched() -> None:
    first = snapshot(
        A,
        [
            holding("X part 1", 0.3, isin=X),
            holding("X part 2", 0.3, isin=X),
            holding("No ISIN", 0.3),
            holding("Short future", -0.1, isin=Y),
            holding("Cash", 0.2, asset_class="cash"),
        ],
    )
    second = snapshot(B, [holding("X", 0.8, isin=X), holding("Y", 0.2, isin=Y)])
    result = pair_overlap(first, second, treatment=AS_REPORTED)
    assert result.overlap == pytest.approx(0.6)
    assert result.unmatched_first == pytest.approx(0.5)
    normalised = pair_overlap(first, second, treatment=WeightTreatment.NORMALISED)
    assert normalised.overlap == pytest.approx(0.6 / 1.0)


def test_pairwise_overlaps_cover_every_pair_in_order() -> None:
    snaps = {C: snapshot(C, F_ROWS), A: snapshot(A, F_ROWS), B: snapshot(B, G_ROWS)}
    pairs = pairwise_overlaps(snaps, treatment=AS_REPORTED)
    assert [(p.first, p.second) for p in pairs] == [(A, B), (A, C), (B, C)]
    assert pairwise_overlaps(list(snaps.values())[:1], treatment=AS_REPORTED) == []


def test_duplicated_exposure_hand_example() -> None:
    lt = _look({A: 0.5, B: 0.5}, {A: snapshot(A, F_ROWS), B: snapshot(B, G_ROWS)})
    weight, isins = duplicated_exposure(lt)
    assert weight == pytest.approx(0.80)
    assert isins == tuple(sorted((X, Y)))


def test_duplicated_exposure_includes_direct_positions() -> None:
    stock_isin = Isin(X)
    stock = fund(stock_isin, instrument_type=InstrumentType.STOCK, ter=None, replication=None,
                 distribution=None, benchmark=None, fund_size=None, currency=USD)  # fmt: skip
    lt = _look(
        {A: 0.5, stock_isin: 0.5},
        {A: snapshot(A, F_ROWS)},
        instruments={A: fund(A), stock_isin: stock},
    )
    weight, isins = duplicated_exposure(lt)
    assert weight == pytest.approx(0.25 + 0.5)
    assert isins == (X,)
    assert duplicated_exposure(_look({A: 1.0}, {A: snapshot(A, F_ROWS)})) == (0.0, ())
