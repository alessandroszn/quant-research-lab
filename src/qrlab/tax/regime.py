"""The common shape of a country's tax analytics (phase 9.1): described, not coded.

A country is a :class:`TaxRegime`. It reads its own ``[parameters.tax]`` keys and returns a
:class:`TaxReport`, which describes the result: sentences (label keys with typed values),
tables with typed columns, the sources in every report language, the date the rules were
checked, and the run's scalars. The report kind writes the CSV tables and the scalars, and the
HTML report renders the section, from this shape alone: a new country adds no rendering code.

Label keys are those of :mod:`qrlab.reporting.labels`; a country adds its own there.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Protocol

from qrlab.core.errors import ValidationError
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import Instrument
from qrlab.portfolio.ledger import LedgerHistory, ToBase
from qrlab.portfolio.transactions import Transaction
from qrlab.portfolio.valuation import Valuation

__all__ = [
    "LANGUAGES",
    "Cell",
    "ColumnKind",
    "Holdings",
    "LabelRef",
    "Paragraph",
    "ParagraphValue",
    "SourcesRef",
    "TaxColumn",
    "TaxInputs",
    "TaxRegime",
    "TaxReport",
    "TaxTable",
]

LANGUAGES = ("en", "it")
"""Report languages; every report gives its sources in each."""


class ColumnKind(Enum):
    """How a column's cells are written: in the CSV and in the report."""

    DATE = "date"  # a date: ISO in the CSV, the report's date format
    YEAR = "year"  # an int
    HOLDING = "holding"  # an ISIN: as is in the CSV, the holding's name in the report
    LABEL = "label"  # a code: as is in the CSV, the label ``prefix + code`` in the report
    TEXT = "text"  # text, as is
    MONEY = "money"  # a Decimal amount (None: "not available"); a float in the CSV
    SHARE = "share"  # a Decimal fraction, shown as a percentage; a float in the CSV


Cell = Decimal | date | int | str | None


@dataclass(frozen=True)
class TaxColumn:
    """One column: its CSV name, its report label key, its kind and its alignment.

    ``label`` may be empty (no header). ``prefix`` applies to :attr:`ColumnKind.LABEL` only.
    """

    key: str
    label: str
    kind: ColumnKind
    align: str
    prefix: str = ""

    def __post_init__(self) -> None:
        """Validate the kind and the alignment."""
        if not isinstance(self.kind, ColumnKind):
            raise ValidationError(f"column {self.key!r}: kind must be a ColumnKind")
        if self.align not in ("left", "right"):
            raise ValidationError(f"column {self.key!r}: align must be 'left' or 'right'")


@dataclass(frozen=True)
class TaxTable:
    """A table of the tax section.

    ``file`` is the CSV the report kind writes (``None``: in the report only), indexed by the
    column ``index``. ``note`` is a label key shown under the table. A table with no rows is
    shown only when ``shown_when_empty``.
    """

    title: str
    columns: tuple[TaxColumn, ...]
    rows: tuple[tuple[Cell, ...], ...]
    file: str | None = None
    index: str | None = None
    note: str | None = None
    shown_when_empty: bool = True

    def __post_init__(self) -> None:
        """Check every row against the columns."""
        width = len(self.columns)
        for row in self.rows:
            if len(row) != width:
                raise ValidationError(
                    f"table {self.title!r}: a row has {len(row)} cells, not {width}"
                )
        if self.file is not None and self.index not in {c.key for c in self.columns}:
            raise ValidationError(f"table {self.title!r}: index {self.index!r} is not a column")


@dataclass(frozen=True)
class LabelRef:
    """A paragraph value that is itself a label key, translated by the report."""

    key: str


@dataclass(frozen=True)
class Holdings:
    """A paragraph value listing holdings by ISIN; the report shows their names."""

    isins: tuple[str, ...]


@dataclass(frozen=True)
class SourcesRef:
    """A paragraph value standing for the report's sources, in the report's language."""


ParagraphValue = str | date | LabelRef | Holdings | SourcesRef


@dataclass(frozen=True)
class Paragraph:
    """A sentence: a label key and the values of its placeholders."""

    key: str
    args: tuple[tuple[str, ParagraphValue], ...] = ()


@dataclass(frozen=True)
class TaxReport:
    """A country's tax analytics of the account, on ``as_of``.

    ``sources`` gives the rules' sources in every language of :data:`LANGUAGES`;
    ``checked_on`` is the date the rules were checked against the law in force. ``scalars``
    are the run record's numbers.
    """

    country: str
    as_of: date
    checked_on: date
    sources: Mapping[str, tuple[str, ...]]
    paragraphs: tuple[Paragraph, ...]
    tables: tuple[TaxTable, ...]
    scalars: Mapping[str, Decimal] = field(default_factory=dict)
    title: str = "tax_title"

    def __post_init__(self) -> None:
        """Require the sources in every report language and unique CSV names."""
        missing = [language for language in LANGUAGES if not self.sources.get(language)]
        if missing:
            raise ValidationError(f"tax report {self.country!r}: no sources in {missing}")
        files = [t.file for t in self.tables if t.file is not None]
        if len(set(files)) != len(files):
            raise ValidationError(f"tax report {self.country!r}: CSV names repeat: {files}")


@dataclass(frozen=True)
class TaxInputs:
    """What any country may need: the account, its instruments and values, and the date."""

    history: LedgerHistory
    transactions: Sequence[Transaction]
    instruments: Mapping[Isin, Instrument]
    valuation: Valuation
    to_base: ToBase
    as_of: date


class TaxRegime(Protocol):
    """A country's tax rules.

    ``keys`` are its required ``[parameters.tax]`` keys besides ``country`` and
    ``optional_keys`` the others; :meth:`parse` turns the table into the country's settings,
    which :meth:`report` then uses.
    """

    country: str
    keys: frozenset[str]
    optional_keys: frozenset[str]

    def parse(self, table: Mapping[str, object]) -> object:
        """Read and check the country's keys (the key names are already checked)."""
        ...  # pragma: no cover - a protocol

    def report(self, inputs: TaxInputs, settings: object) -> TaxReport:
        """Return the tax analytics of the account."""
        ...  # pragma: no cover - a protocol
