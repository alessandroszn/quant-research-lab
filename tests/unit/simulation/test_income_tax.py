"""A yearly tax on the income of the holdings in projections (design 9.2), by hand."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.simulation import Plan, SimulatedReturns, TaxModel, project
from qrlab.tax import swiss_tax_model


def _plan(taxes: TaxModel) -> Plan:
    return Plan(
        initial_wealth=1000.0,
        currency=Currency("CHF"),
        weights=pd.Series([1.0], index=["fund"]),
        periods_per_year=1,
        flows=(),
        flow_timing="end",
        rebalance_every=None,
        annual_cost=0.0,
        inflation=0.0,
        taxes=taxes,
    )


ZERO = SimulatedReturns(np.zeros((1, 2, 1)), ("fund",), "fixed")


def test_two_years_by_hand() -> None:
    """0.30 x 0.02 = 0.6 % a year: 1,000 -> 994 -> 988.036; taxes 6 + 5.964 = 11.964."""
    out = project(
        _plan(swiss_tax_model(wealth_tax_rate=0.0, income_tax_rate=0.3, taxable_yield=0.02)), ZERO
    )
    assert out.nominal[0].tolist() == pytest.approx([1000.0, 994.0, 988.036], abs=1e-9)
    assert out.taxes_paid[0] == pytest.approx(11.964, abs=1e-9)


def test_with_the_wealth_tax_both_are_paid() -> None:
    """0.3 % wealth tax + 0.6 % income tax = 0.9 % a year: 1,000 -> 991."""
    taxes = swiss_tax_model(wealth_tax_rate=0.003, income_tax_rate=0.3, taxable_yield=0.02)
    assert taxes.capital_gains_rate == 0.0
    assert project(_plan(taxes), ZERO).nominal[0][1] == pytest.approx(991.0, abs=1e-9)


def test_zero_income_tax_changes_nothing(rng: np.random.Generator) -> None:
    returns = SimulatedReturns(rng.normal(0.004, 0.05, (50, 24, 1)), ("fund",), "rnd")
    plain = project(_plan(TaxModel(0.26, 0.002)), returns)
    zero = project(_plan(TaxModel(0.26, 0.002, income_tax_rate=0.0, taxable_yield=0.0)), returns)
    for name in ("nominal", "taxes_paid", "liquidation_value"):
        assert np.array_equal(getattr(plain, name), getattr(zero, name)), name


@pytest.mark.parametrize("name", ["income_tax_rate", "taxable_yield"])
def test_the_rates_are_validated(name: str) -> None:
    with pytest.raises(ValidationError, match=name):
        TaxModel(0.0, 0.0, **{name: 1.0})  # type: ignore[arg-type]
