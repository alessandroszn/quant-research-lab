"""Capital losses carried forward, the Italian way, for projections and backtests (8.6b).

Under the Italian rules (see :mod:`qrlab.tax.italy` for sources), a gain on a fund or ETF is
capital income: it is taxed in full and uses no losses. Every realised loss, on any asset,
goes into a balance; a gain on any other asset (a share, a bond, an ETC) is reduced by the
losses realised in the same sale first, then by the balance, oldest year first, within
``carry_years`` after the year a loss was realised.

For a portfolio of funds only the rules change no number: fund gains never use losses. The
calculations are written so that this holds bit for bit, which the tests check.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from qrlab.core.errors import ValidationError

__all__ = ["LossBalance", "LossRules", "fund_mask", "realised_tax"]


@dataclass(frozen=True)
class LossRules:
    """How realised losses are carried.

    Parameters
    ----------
    carry_years
        A loss realised in year ``y`` can be used until year ``y + carry_years`` (4 in Italy).
    fund_assets
        Assets whose gains are capital income (funds and ETFs): taxed in full, using no losses.
    """

    carry_years: int
    fund_assets: frozenset[str]

    def __post_init__(self) -> None:
        """Validate the rules."""
        if type(self.carry_years) is not int or self.carry_years < 0:
            raise ValidationError("carry_years must be an int >= 0")
        assets: object = self.fund_assets
        if not isinstance(assets, frozenset) or not all(isinstance(a, str) for a in assets):
            raise ValidationError("fund_assets must be a frozenset of asset names")


def fund_mask(rules: LossRules, assets: Sequence[str]) -> np.ndarray:
    """Return which ``assets`` are funds; an unknown name in the rules raises."""
    unknown = sorted(rules.fund_assets - set(assets))
    if unknown:
        raise ValidationError(f"fund_assets {unknown} are not assets {list(assets)}")
    return np.array([a in rules.fund_assets for a in assets], dtype=bool)


class LossBalance:
    """Unused losses by year of realisation, per path (an array of paths x years)."""

    def __init__(self, *, paths: int, years: int, carry_years: int) -> None:
        """Start with no losses."""
        self.lots = np.zeros((paths, years))
        self.carry_years = carry_years

    def _usable(self, year: int) -> range:
        return range(max(0, year - self.carry_years), year + 1)

    def available(self, year: int) -> np.ndarray:
        """Return the losses usable in ``year``, per path."""
        window = self._usable(year)
        return np.asarray(self.lots[:, window.start : window.stop].sum(axis=1), dtype=np.float64)

    def add(self, year: int, amount: np.ndarray) -> None:
        """Record losses realised in ``year``."""
        self.lots[:, year] += amount

    def use(self, year: int, amount: np.ndarray) -> np.ndarray:
        """Use up to ``amount`` of the losses usable in ``year``, oldest first; return the use."""
        needed = amount.copy()
        used = np.zeros_like(needed)
        for lot in self._usable(year):
            take = np.minimum(self.lots[:, lot], needed)
            self.lots[:, lot] -= take
            needed -= take
            used += take
        return used


def realised_tax(
    gains: np.ndarray, rate: float, funds: np.ndarray, balance: LossBalance, year: int
) -> np.ndarray:
    """Return the tax on one sale's realised results (paths x assets), updating the balance.

    Fund gains are taxed in full. The other gains, net of every loss realised in the same sale,
    use the balance; a net loss joins it.
    """
    positive = np.clip(gains, 0.0, None)
    fund_gain = positive[:, funds].sum(axis=1)
    other = positive[:, ~funds].sum(axis=1) - np.clip(-gains, 0.0, None).sum(axis=1)
    balance.add(year, np.clip(-other, 0.0, None))
    taxable = np.clip(other, 0.0, None)
    taxable = taxable - balance.use(year, taxable)
    return np.asarray(rate * (fund_gain + taxable), dtype=np.float64)
