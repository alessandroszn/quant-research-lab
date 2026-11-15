"""The countries with tax analytics, by code (phase 9.1)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from qrlab.core.errors import ValidationError
from qrlab.tax.custom import CUSTOM
from qrlab.tax.italy import ITALY
from qrlab.tax.regime import TaxRegime
from qrlab.tax.switzerland import SWITZERLAND

__all__ = ["REGIMES", "regime_for"]

REGIMES: Mapping[str, TaxRegime] = MappingProxyType(
    {ITALY.country: ITALY, SWITZERLAND.country: SWITZERLAND, CUSTOM.country: CUSTOM}
)
"""Country code (ISO 3166-1 alpha-2, lower case) to its tax rules; ``"custom"`` is the
configurable model (phase 9.3), for any other country."""


def regime_for(country: object) -> TaxRegime:
    """Return the tax rules of ``country``; an unknown code raises with the list."""
    if not isinstance(country, str) or country not in REGIMES:
        raise ValidationError(
            f"[parameters.tax] country must be one of {sorted(REGIMES)}, got {country!r}"
        )
    return REGIMES[country]
