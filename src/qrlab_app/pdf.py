"""Export a run's report as a PDF, with Qt's own text engine (design note 12.4).

Qt lays out a subset of HTML, so the report's HTML goes through a small print adapter first.
The adapter changes only the layout, never a word or a number:

- each figure gets the page's text width, in a paragraph of its own;
- the report's style sheet, written for browsers, is replaced by :data:`PRINT_STYLE`, written
  for Qt (which reads only part of CSS, and no ``rem``); tables get an explicit cell padding
  and are set a point smaller than the text;
- a report with a table of more than :data:`WIDE_TABLE` columns is printed in landscape.

The first line of the PDF says it is a print of the report of that run, and when it was made.
The PDF is written where the user chooses, never into the run's output folder.
"""

from __future__ import annotations

import html as html_module
import re
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

__all__ = [
    "MARGIN_MM",
    "PRINT_STYLE",
    "WIDE_TABLE",
    "adapt_html",
    "export_pdf",
    "is_wide",
    "max_columns",
    "text_width",
]

MARGIN_MM = 20
"""Page margin on every side, in millimetres: the 2 cm ``QTextDocument.print_`` always keeps
(the PDF writer itself adds none)."""
WIDE_TABLE = 6
"""A report with a table of more columns than this is printed in landscape."""
_A4_MM = (210, 297)
_LAYOUT_DPI = 96  # QTextDocument lays a page out in pixels at 96 per inch
PRINT_STYLE = (
    'body { font-family: "Segoe UI", "DejaVu Sans", Arial, sans-serif; font-size: 9pt; '
    "color: #1d1d1f; } "
    "h1 { font-size: 16pt; } h2 { font-size: 13pt; } h3 { font-size: 10pt; } "
    "table { font-size: 8pt; } th { background-color: #f0f0f3; } "
    "td.right, th.right { text-align: right; } "
    "p.note, dt, footer { color: #555555; }"
)
"""The style sheet the PDF uses instead of the report's (Qt reads a subset of CSS)."""
_ROW = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<t[hd]\b", re.IGNORECASE)


def max_columns(html: str) -> int:
    """Return the most cells in one table row of ``html`` (0 without tables)."""
    return max((len(_CELL.findall(row)) for row in _ROW.findall(html)), default=0)


def is_wide(html: str) -> bool:
    """Return whether the report is printed in landscape (a table wider than 6 columns)."""
    return max_columns(html) > WIDE_TABLE


def text_width(landscape: bool) -> int:
    """Return the width of an A4 page's text, in the pixels Qt lays the document out in."""
    page_mm = _A4_MM[1] if landscape else _A4_MM[0]
    return int((page_mm - 2 * MARGIN_MM) / 25.4 * _LAYOUT_DPI)


def adapt_html(html: str, *, image_width: int, header: str) -> str:
    """Return ``html`` laid out for Qt's text engine, with ``header`` as its first line."""
    adapted = re.sub(r"<figure\b[^>]*>", "<p>", html, flags=re.IGNORECASE)
    adapted = re.sub(r"</figure>", "</p>", adapted, flags=re.IGNORECASE)
    adapted = re.sub(r"<figcaption\b[^>]*>", "<br>", adapted, flags=re.IGNORECASE)
    adapted = re.sub(r"</figcaption>", "", adapted, flags=re.IGNORECASE)
    adapted = re.sub(r"<img\b", f'<img width="{image_width}"', adapted, flags=re.IGNORECASE)
    adapted = re.sub(r"<style\b.*?</style>", "", adapted, flags=re.IGNORECASE | re.DOTALL)
    adapted = re.sub(
        r"<table\b", '<table cellpadding="3" cellspacing="0"', adapted, flags=re.IGNORECASE
    )
    first = f'<p class="note">{html_module.escape(header)}</p>'
    body = re.search(r"<body\b[^>]*>", adapted, flags=re.IGNORECASE)
    if body is None:
        return first + adapted
    return adapted[: body.end()] + first + adapted[body.end() :]


def export_pdf(report: Path, target: Path, *, header: str, title: str) -> QTextDocument:
    """Write ``report`` (an HTML file) to ``target`` as an A4 PDF; return the laid-out document.

    Raises
    ------
    OSError
        When the report cannot be read or the PDF cannot be written.
    """
    html = Path(report).read_text(encoding="utf-8")
    landscape = is_wide(html)
    document = QTextDocument()
    document.setDefaultStyleSheet(PRINT_STYLE)
    width = int(text_width(landscape) * 0.95)  # a little room for the figure's own margin
    document.setHtml(adapt_html(html, image_width=width, header=header))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(target))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    orientation = (
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait
    )
    writer.setPageOrientation(orientation)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(title)
    writer.setCreator("Quant Research Lab")
    document.print_(writer)
    del writer  # the file is complete once the writer is gone
    if not target.is_file():
        raise OSError(f"the PDF could not be written to {target}")
    return document
