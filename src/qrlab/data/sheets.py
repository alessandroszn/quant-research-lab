"""Spreadsheet files as issuers publish them (phases 8.2b and 8.2c).

Excel workbooks (xlsx), XML spreadsheets (SpreadsheetML 2003, which iShares serves as
``.xls``) and numbers written with symbols.

Shared by the price parser (:mod:`qrlab.data.user_csv`) and the holdings parser
(:mod:`qrlab.instruments.io`).
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Sequence
from enum import Enum

import openpyxl

from qrlab.core.errors import ValidationError
from qrlab.data.errors import ParseError

__all__ = [
    "FileFormat",
    "check_affixes",
    "read_spreadsheetml_rows",
    "read_xlsx_rows",
    "strip_affixes",
]


class FileFormat(Enum):
    """The kind of file a mapping reads."""

    CSV = "csv"
    XLSX = "xlsx"  # an Excel workbook, read with openpyxl
    SPREADSHEETML = "spreadsheetml"  # an XML Spreadsheet 2003, read with the standard library


_SS = "urn:schemas-microsoft-com:office:spreadsheet"
_DECLARATION = re.compile(rb"<!(DOCTYPE|ENTITY)", re.IGNORECASE)


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


def read_spreadsheetml_rows(content: bytes, *, sheet: str, skip_rows: int) -> list[list[object]]:
    """Return the header and the rows after the preamble of one sheet of an XML spreadsheet.

    The format is Microsoft's XML Spreadsheet 2003 (``urn:schemas-microsoft-com:office:
    spreadsheet``). Leading byte-order marks are skipped. A file with a DOCTYPE or an entity
    declaration is refused before parsing, so no entity is ever expanded. Numeric cells are
    read as floats and the others as text; a cell placed with ``ss:Index`` lands in its column
    (the cells skipped are empty). Rows are trimmed as in :func:`read_xlsx_rows`.
    """
    body = content
    while body.startswith(b"\xef\xbb\xbf"):
        body = body[3:]
    if _DECLARATION.search(body):
        raise ParseError("DOCTYPE or entity declarations are refused in an XML spreadsheet")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ParseError("content is not a valid XML spreadsheet") from exc
    if root.tag != f"{{{_SS}}}Workbook":
        raise ParseError("content is not a valid XML spreadsheet (no ss:Workbook)")
    sheets = {ws.get(f"{{{_SS}}}Name"): ws for ws in root.findall(f"{{{_SS}}}Worksheet")}
    if sheet not in sheets:
        raise ParseError(f"no sheet {sheet!r} in the workbook: {list(sheets)}")
    rows = [_xml_row(row) for row in sheets[sheet].iter(f"{{{_SS}}}Row")]
    if len(rows) <= skip_rows:
        raise ParseError(f"file has no header after skipping {skip_rows} line(s)")
    body_rows = rows[skip_rows:]
    header = next((row for row in body_rows if _filled_width(row)), body_rows[0])
    width = _filled_width(header)
    return [row[: max(width, _filled_width(row))] for row in body_rows]


def _xml_row(row: ET.Element) -> list[object]:
    """Return a row's cells, placed by ``ss:Index`` (1-based) when a cell gives one."""
    cells: list[object] = []
    for cell in row.findall(f"{{{_SS}}}Cell"):
        index = cell.get(f"{{{_SS}}}Index")
        if index is not None:
            cells.extend([None] * (int(index) - 1 - len(cells)))
        data = cell.find(f"{{{_SS}}}Data")
        if data is None:
            cells.append(None)
        elif data.get(f"{{{_SS}}}Type") == "Number":
            cells.append(float(data.text or "nan"))
        else:
            cells.append(data.text or "")
    return cells


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
