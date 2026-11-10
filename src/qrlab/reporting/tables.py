"""Report tables: already formatted text cells with explicit column alignment."""

from __future__ import annotations

from dataclasses import dataclass

from qrlab.core.errors import ValidationError

__all__ = ["Table"]

_ALIGNMENTS = frozenset({"left", "right"})


@dataclass(frozen=True)
class Table:
    """A table of formatted text.

    Parameters
    ----------
    title
        Caption.
    columns
        Column headers (at least one).
    rows
        Rows of text cells, each as long as ``columns``. Numbers are formatted beforehand with
        :mod:`qrlab.reporting.formatting`, so a table never decides how to round.
    align
        ``"left"`` or ``"right"`` per column (numbers right-aligned).
    notes
        Footnotes shown under the table.
    """

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    align: tuple[str, ...]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate shape, alignment and cell types."""
        if not self.columns:
            raise ValidationError("a table needs at least one column")
        if len(self.align) != len(self.columns) or not set(self.align) <= _ALIGNMENTS:
            raise ValidationError("align needs 'left' or 'right' for every column")
        for number, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ValidationError(
                    f"row {number} has {len(row)} cells for {len(self.columns)} columns"
                )
            if not all(isinstance(cell, str) for cell in row):
                raise ValidationError(f"row {number}: every cell must be formatted text")
