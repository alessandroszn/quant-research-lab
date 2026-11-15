"""Spreadsheet files as issuers publish them (phase 8.2): xlsx sheets and numbers with symbols.

Shared by the price parser (:mod:`qrlab.data.user_csv`) and the holdings parser
(:mod:`qrlab.instruments.io`).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from enum import Enum

import openpyxl

from qrlab.core.errors import ValidationError
from qrlab.data.errors import ParseError

__all__ = ["FileFormat", "check_affixes", "read_xlsx_rows", "strip_affixes"]


class FileFormat(Enum):
    """The kind of file a mapping reads."""

    CSV = "csv"
    XLSX = "xlsx"  # an Excel workbook, read with openpyxl


def read_xlsx_rows(content: bytes, *, sheet: str, skip_rows: int) -> list[list[object]]:
    """Return the header and the rows after the preamble of one sheet of an xlsx workbook.

    Rows are trimmed to the header's width (the first non-empty row after the preamble) when the
    cells beyond it are empty; a non-empty cell beyond it keeps the row longer, so that a
    field-count check reports it. Blank rows are kept, so positions still give line numbers.
    Cell values are as openpyxl reads them (text, numbers, dates or ``None``).
    """
    try:
        book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (zipfile.BadZipFile, OSError, KeyError, ValueError) as exc:
        raise ParseError("content is not a valid xlsx workbook") from exc
    try:
        if sheet not in book.sheetnames:
            raise ParseError(f"no sheet {sheet!r} in the workbook: {book.sheetnames}")
        rows = [list[object](row) for row in book[sheet].iter_rows(values_only=True)]
    finally:
        book.close()
    if len(rows) <= skip_rows:
        raise ParseError(f"file has no header after skipping {skip_rows} line(s)")
    body = rows[skip_rows:]
    header = next((row for row in body if _filled_width(row)), body[0])
    width = _filled_width(header)
    return [row[: max(width, _filled_width(row))] for row in body]


def check_affixes(affixes: object) -> tuple[str, ...]:
    """Return declared number affixes (``%``, ``$``, ``€`` ...) or raise.

    An affix is non-empty text with no digit, sign, separator or space, so that removing it can
    never change the number.
    """
    if not isinstance(affixes, (list, tuple)) or not all(isinstance(a, str) for a in affixes):
        raise ValidationError(f"value_affixes must be a list of text, got {affixes!r}")
    for affix in affixes:
        if not affix or any(c.isdigit() or c in "-+.,' " for c in affix):
            raise ValidationError(
                f"value_affixes {affix!r}: an affix has no digit, sign, separator or space"
            )
    return tuple(affixes)


def strip_affixes(text: str, affixes: Sequence[str], line: int) -> str:
    """Remove one declared affix at the start (after a minus sign) and one at the end.

    ``"-$5.00"`` with ``("$",)`` gives ``"-5.00"``; an affix elsewhere is left in place, so the
    number parser rejects it. Text that is only an affix raises.
    """
    if not affixes:
        return text
    body = text.strip()
    sign = ""
    if body.startswith("-"):
        sign, body = "-", body[1:]
    stripped = False
    for affix in affixes:
        if body.startswith(affix):
            body, stripped = body[len(affix) :], True
            break
    for affix in affixes:
        if body.endswith(affix):
            body, stripped = body[: -len(affix)], True
            break
    if stripped and not body.strip():
        raise ParseError(f"line {line}: {text.strip()!r} has a symbol but no number")
    return sign + body


def _filled_width(row: Sequence[object]) -> int:
    """Return the position after the last non-empty cell."""
    for position in range(len(row), 0, -1):
        cell = row[position - 1]
        if cell is not None and str(cell).strip():
            return position
    return 0
