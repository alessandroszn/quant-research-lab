"""Checks through fund holdings and tracking series (phase 2.5). All data synthetic.

Hand values (design note 2.5): fund A at 60 % (US 0.6, JP 0.4) and fund B at 30 % (US 0.5,
DE 0.5) with 10 % cash give a largest country of US 0.51; f = {X 0.5, Y 0.3, Z 0.2} and
g = {X 0.4, Y 0.4, W 0.2} overlap 0.70 and, each at 0.5, duplicate 0.80; a fund returning 9.8 %
against 10.0 % over 365 days has TD -0.20 % and, with TER 0.20 %, TD + TER = 0; monthly
differences of +-0.1 % give TE 0.40 %; holdings dated 30 days before as_of are stale when the
limit is 29 days and not when it is 30.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
import pytest

from qrlab.checks import holdings_checks as hc
from qrlab.checks.engine import ALL_CHECKS
from qrlab.checks.framework import Measurement, NotApplicable
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.data.user_csv import PriceType
from qrlab.instruments.identifiers import Isin
from qrlab.lookthrough.inputs import LookThroughInputs
from qrlab.lookthrough.tracking import TrackingSeries
from support.checks import AS_OF, A, B, C, fund, weighted_context
from support.lookthrough import W, X, Y, Z, countries, holding, snapshot, with_lookthrough

NO_PARAMS: Mapping[str, object] = {}
EUR = Currency("EUR")
F_ROWS = [holding("X", 0.5, isin=X), holding("Y", 0.3, isin=Y), holding("Z", 0.2, isin=Z)]
G_ROWS = [holding("X", 0.4, isin=X), holding("Y", 0.4, isin=Y), holding("W", 0.2, isin=W)]
ALL_RUNNERS = (
    (hc.country, NO_PARAMS),
    (hc.sector, NO_PARAMS),
    (hc.issuer, NO_PARAMS),
    (hc.pair_overlap, NO_PARAMS),
    (hc.duplicated, NO_PARAMS),
    (hc.tracking_difference_check, NO_PARAMS),
    (hc.tracking_error_check, {"periods_per_year": 12}),
    (hc.ter_gap, NO_PARAMS),
    (hc.stale_holdings, {"max_age_days": 30}),
)


def _one(outcome: list[Measurement] | NotApplicable) -> Measurement:
    assert not isinstance(outcome, NotApplicable), outcome
    (measurement,) = outcome
    return measurement


def _series(levels: Mapping[date, float], price_type: PriceType) -> TrackingSeries:
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in levels])
    return TrackingSeries(pd.Series(list(levels.values()), index=index), price_type, EUR, None)


def _one_year(fund_end: float, index_end: float) -> tuple[TrackingSeries, TrackingSeries]:
    dates = (AS_OF - timedelta(days=365), AS_OF)
    return (
        _series(dict(zip(dates, (100.0, fund_end), strict=True)), PriceType.NAV),
        _series(dict(zip(dates, (100.0, index_end), strict=True)), PriceType.TOTAL_RETURN),
    )


def test_registry_has_the_nine_checks() -> None:
    ids = {spec.id for spec in hc.CHECKS}
    assert len(ids) == 9
    assert ids <= {spec.id for spec in ALL_CHECKS}


def test_every_check_is_not_applicable_without_lookthrough() -> None:
    ctx = weighted_context({A: "1"})
    for runner, params in ALL_RUNNERS:
        assert runner(ctx, params) == NotApplicable("no look-through inputs given"), runner


def test_country_concentration_hand_example() -> None:
    ctx = with_lookthrough(
        weighted_context({A: "0.6", B: "0.3"}),
        {A: countries(A, {"US": 0.6, "JP": 0.4}), B: countries(B, {"US": 0.5, "DE": 0.5})},
    )
    measured = _one(hc.country(ctx, NO_PARAMS))
    assert measured.observed == pytest.approx(0.51)
    assert measured.details["country"] == "US"
    assert measured.details["unknown"] == "0.000000"
    assert hc.sector(ctx, NO_PARAMS) == NotApplicable("no sector known through holdings")
    issuer = _one(hc.issuer(ctx, NO_PARAMS))
    assert issuer.details["grouping"] == "security, not issuer (no issuer map)"


def test_issuer_with_a_map_and_sector() -> None:
    rows = [
        holding("Alpha A", 0.3, isin=X, sector="Tech"),
        holding("Alpha C", 0.3, isin=Y, sector="Tech"),
        holding("Beta", 0.4, isin=Z, sector="Energy"),
    ]
    issuers = {Isin(X): "Alpha", Isin(Y): "Alpha"}
    ctx = with_lookthrough(weighted_context({A: "1"}), {A: snapshot(A, rows)}, issuers=issuers)
    issuer = _one(hc.issuer(ctx, NO_PARAMS))
    assert issuer.observed == pytest.approx(0.6)
    assert issuer.details["issuer"] == "Alpha"
    assert "grouping" not in issuer.details
    assert _one(hc.sector(ctx, NO_PARAMS)).observed == pytest.approx(0.6)


def test_overlap_and_duplicated_hand_example() -> None:
    ctx = with_lookthrough(
        weighted_context({A: "0.5", B: "0.5"}), {A: snapshot(A, F_ROWS), B: snapshot(B, G_ROWS)}
    )
    pair = _one(hc.pair_overlap(ctx, NO_PARAMS))
    assert pair.subject == f"{A.code} / {B.code}"
    assert pair.observed == pytest.approx(0.70)
    assert pair.details == {"unmatched": "0.000000 / 0.000000"}
    assert _one(hc.duplicated(ctx, NO_PARAMS)).observed == pytest.approx(0.80)
    single = with_lookthrough(weighted_context({A: "1"}), {A: snapshot(A, F_ROWS)})
    assert hc.pair_overlap(single, NO_PARAMS) == NotApplicable(
        "needs holdings of at least two funds"
    )


def test_tracking_hand_example() -> None:
    ctx = with_lookthrough(
        weighted_context({A: "0.5", B: "0.4"}, instruments={A: fund(A), B: fund(B, ter=None)}),
        {},
        tracking={A: _one_year(109.8, 110.0), B: _one_year(110.0, 110.0), C: _one_year(1, 1)},
    )
    by_fund = {m.subject: m for m in hc.tracking_difference_check(ctx, NO_PARAMS)}  # type: ignore[union-attr]
    assert set(by_fund) == {A.code, B.code}  # C is not held
    assert by_fund[A.code].observed == pytest.approx(-0.002)
    gap = _one(hc.ter_gap(ctx, NO_PARAMS))  # B has no TER
    assert gap.subject == A.code
    assert gap.observed == pytest.approx(0.0, abs=1e-12)


def test_tracking_needs_a_year_and_a_ter() -> None:
    dates = (AS_OF - timedelta(days=180), AS_OF)
    short = (
        _series(dict(zip(dates, (100.0, 101.0), strict=True)), PriceType.NAV),
        _series(dict(zip(dates, (100.0, 101.0), strict=True)), PriceType.TOTAL_RETURN),
    )
    ctx = with_lookthrough(weighted_context({A: "1"}), {}, tracking={A: short})
    reason = NotApplicable("no held fund has a year of tracking data")
    assert hc.tracking_difference_check(ctx, NO_PARAMS) == reason
    assert hc.ter_gap(ctx, NO_PARAMS) == reason
    no_ter = with_lookthrough(
        weighted_context({A: "1"}, instruments={A: fund(A, ter=None)}),
        {},
        tracking={A: _one_year(109.8, 110.0)},
    )
    assert hc.ter_gap(no_ter, NO_PARAMS) == NotApplicable("no tracked fund has a known TER")


def test_tracking_error_hand_example() -> None:
    dates = [AS_OF - timedelta(days=30 * k) for k in range(4, -1, -1)]
    levels = [100.0]
    for diff in (0.001, -0.001, 0.001, -0.001):
        levels.append(levels[-1] * (1 + diff))
    pair = (
        _series(dict(zip(dates, levels, strict=True)), PriceType.TOTAL_RETURN),
        _series(dict.fromkeys(dates, 100.0), PriceType.TOTAL_RETURN),
    )
    one_return = (
        _series(dict(zip(dates[-2:], levels[-2:], strict=True)), PriceType.NAV),
        _series(dict.fromkeys(dates[-2:], 100.0), PriceType.TOTAL_RETURN),
    )
    ctx = with_lookthrough(
        weighted_context({A: "0.5", B: "0.5"}), {}, tracking={A: pair, B: one_return, C: pair}
    )
    measured = _one(hc.tracking_error_check(ctx, {"periods_per_year": 12}))
    assert measured.subject == A.code
    assert measured.observed == pytest.approx(0.004)
    too_short = with_lookthrough(weighted_context({B: "1"}), {}, tracking={B: one_return})
    assert isinstance(hc.tracking_error_check(too_short, {"periods_per_year": 12}), NotApplicable)
    with pytest.raises(ValidationError, match="periods_per_year"):
        hc.tracking_error_check(ctx, {"periods_per_year": "12"})


def test_stale_holdings_boundary() -> None:
    ctx = with_lookthrough(weighted_context({A: "1"}), {A: countries(A, {"US": 1.0})})
    assert (AS_OF - date(2026, 5, 31)).days == 30
    stale = _one(hc.stale_holdings(ctx, {"max_age_days": 29}))
    assert stale.observed == 1.0
    assert stale.details == {"funds": f"{A.code} (2026-05-31)"}
    assert _one(hc.stale_holdings(ctx, {"max_age_days": 30})).observed == 0.0
    with pytest.raises(ValidationError, match="max_age_days"):
        hc.stale_holdings(ctx, {"max_age_days": -1})


def test_lookthrough_inputs_are_validated() -> None:
    ctx = with_lookthrough(weighted_context({A: "1"}), {A: countries(A, {"US": 1.0})})
    assert ctx.lookthrough is not None
    with pytest.raises(ValidationError, match="exactly the holdings"):
        LookThroughInputs(ctx.lookthrough.exposures, {}, {})
    later = replace(ctx.lookthrough.exposures, as_of=date(2026, 7, 1))
    with pytest.raises(ValidationError, match="look-through is as of"):
        replace(ctx, lookthrough=replace(ctx.lookthrough, exposures=later))
