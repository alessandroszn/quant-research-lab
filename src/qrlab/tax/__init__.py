"""Tax analytics of a securities account (phase 8.6): analytics, not tax advice."""

from qrlab.tax.italy import (
    Category,
    LossLot,
    Regime,
    TaxEvent,
    TaxPosition,
    italian_tax_position,
)

__all__ = ["Category", "LossLot", "Regime", "TaxEvent", "TaxPosition", "italian_tax_position"]
