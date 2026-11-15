"""Tax analytics of a securities account (phases 8.6 and 9.1): analytics, not tax advice.

Every country is a :class:`~qrlab.tax.regime.TaxRegime` returning a
:class:`~qrlab.tax.regime.TaxReport`; :data:`REGIMES` lists them by country code.
"""

from qrlab.tax.italy import (
    ITALY,
    Category,
    ItalianRegime,
    ItalianSettings,
    LossLot,
    Regime,
    TaxEvent,
    TaxPosition,
    italian_tax_position,
    italian_tax_report,
)
from qrlab.tax.regime import (
    ColumnKind,
    Holdings,
    LabelRef,
    Paragraph,
    SourcesRef,
    TaxColumn,
    TaxInputs,
    TaxRegime,
    TaxReport,
    TaxTable,
)
from qrlab.tax.regimes import REGIMES, regime_for

__all__ = [
    "ITALY",
    "REGIMES",
    "Category",
    "ColumnKind",
    "Holdings",
    "ItalianRegime",
    "ItalianSettings",
    "LabelRef",
    "LossLot",
    "Paragraph",
    "Regime",
    "SourcesRef",
    "TaxColumn",
    "TaxEvent",
    "TaxInputs",
    "TaxPosition",
    "TaxRegime",
    "TaxReport",
    "TaxTable",
    "italian_tax_position",
    "italian_tax_report",
    "regime_for",
]
