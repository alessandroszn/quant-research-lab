"""Tax analytics of a securities account (phases 8.6, 9.1-9.3, 11.3): analytics, not tax advice.

Every country is a :class:`~qrlab.tax.regime.TaxRegime` returning a
:class:`~qrlab.tax.regime.TaxReport`; :data:`REGIMES` lists them by country code.
"""

from qrlab.tax.custom import CUSTOM, CustomRegime, CustomSettings, custom_tax_model
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
from qrlab.tax.italy_wealth import (
    Custody,
    Statements,
    WealthItem,
    WealthTaxes,
    WealthYear,
    Where,
    wealth_taxes,
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
from qrlab.tax.switzerland import SWITZERLAND, SwissRegime, SwissSettings, swiss_tax_model

__all__ = [
    "CUSTOM",
    "ITALY",
    "REGIMES",
    "SWITZERLAND",
    "Category",
    "ColumnKind",
    "Custody",
    "CustomRegime",
    "CustomSettings",
    "Holdings",
    "ItalianRegime",
    "ItalianSettings",
    "LabelRef",
    "LossLot",
    "Paragraph",
    "Regime",
    "SourcesRef",
    "Statements",
    "SwissRegime",
    "SwissSettings",
    "TaxColumn",
    "TaxEvent",
    "TaxInputs",
    "TaxPosition",
    "TaxRegime",
    "TaxReport",
    "TaxTable",
    "WealthItem",
    "WealthTaxes",
    "WealthYear",
    "Where",
    "custom_tax_model",
    "italian_tax_position",
    "italian_tax_report",
    "regime_for",
    "swiss_tax_model",
    "wealth_taxes",
]
