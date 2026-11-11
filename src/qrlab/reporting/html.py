"""Self-contained HTML rendering of reports.

The output is one file: inline CSS, figures embedded as base64 PNG, no scripts, fonts, links or
any other external resource, so opening a report never contacts the network and never leaks
data. Every text value is escaped. Output is deterministic for identical inputs.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from qrlab.core.errors import ValidationError
from qrlab.reporting.formatting import Language, escape
from qrlab.reporting.tables import Table

__all__ = ["Figure", "Report", "Section", "render_html", "write_report"]

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CSS = """
body { font-family: "DejaVu Sans", "Segoe UI", Arial, sans-serif; margin: 2rem auto;
       max-width: 60rem; color: #1d1d1f; line-height: 1.45; padding: 0 1rem; }
h1 { font-size: 1.6rem; margin-bottom: 0.2rem; }
h2 { font-size: 1.2rem; border-bottom: 1px solid #d0d0d5; padding-bottom: 0.2rem;
     margin-top: 2rem; }
h3 { font-size: 1rem; margin-bottom: 0.3rem; }
dl.facts { display: grid; grid-template-columns: max-content auto; gap: 0.1rem 1rem; }
dl.facts dt { color: #555; }
dl.facts dd { margin: 0; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; font-size: 0.9rem; }
th, td { border-bottom: 1px solid #e5e5ea; padding: 0.3rem 0.5rem; text-align: left; }
th { background: #f5f5f7; }
td.right, th.right { text-align: right; font-variant-numeric: tabular-nums; }
p.note { color: #555; font-size: 0.85rem; margin: 0.2rem 0; }
section.warnings { border: 1px solid #c77700; background: #fff8e6; padding: 0.5rem 1rem; }
figure { margin: 1rem 0; }
figure img { max-width: 100%; height: auto; }
footer { margin-top: 2.5rem; color: #555; font-size: 0.85rem; border-top: 1px solid #d0d0d5; }
""".strip()


@dataclass(frozen=True)
class Figure:
    """A PNG image with a caption."""

    title: str
    png: bytes

    def __post_init__(self) -> None:
        """Accept PNG bytes only."""
        if not self.png.startswith(_PNG_SIGNATURE):
            raise ValidationError("figures must be PNG bytes")


@dataclass(frozen=True)
class Section:
    """A titled block of paragraphs, tables and figures (rendered in that order)."""

    title: str
    paragraphs: tuple[str, ...]
    tables: tuple[Table, ...]
    figures: tuple[Figure, ...]


@dataclass(frozen=True)
class Report:
    """A complete report: header facts, visible warnings, sections and footer lines."""

    title: str
    language: Language
    facts: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]
    sections: tuple[Section, ...]
    footer: tuple[str, ...]


def render_html(report: Report) -> str:
    """Render ``report`` as one self-contained HTML document."""
    parts = [
        "<!DOCTYPE html>",
        f'<html lang="{report.language.value}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(report.title)}</title>",
        f"<style>\n{_CSS}\n</style>",
        "</head>",
        "<body>",
        "<header>",
        f"<h1>{escape(report.title)}</h1>",
        '<dl class="facts">',
        *(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in report.facts),
        "</dl>",
        "</header>",
    ]
    if report.warnings:
        parts += ['<section class="warnings">', "<ul>"]
        parts += [f"<li>{escape(w)}</li>" for w in report.warnings]
        parts += ["</ul>", "</section>"]
    parts.append("<main>")
    for section in report.sections:
        parts += _section(section)
    parts += ["</main>", "<footer>"]
    parts += [f"<p>{escape(line)}</p>" for line in report.footer]
    parts += ["</footer>", "</body>", "</html>", ""]
    return "\n".join(parts)


def write_report(report: Report, path: Path, *, overwrite: bool) -> Path:
    """Write the rendered report to ``path`` (UTF-8).

    Keep reports with real data in git-ignored folders (``results/``, ``reports/``, ``data/``).

    Raises
    ------
    ValidationError
        If ``path`` exists and ``overwrite`` is False.
    """
    target = Path(path)
    if target.exists() and not overwrite:
        raise ValidationError(f"{target} already exists; pass overwrite=True to replace it")
    target.write_text(render_html(report), encoding="utf-8", newline="\n")
    return target


def _section(section: Section) -> list[str]:
    parts = ["<section>", f"<h2>{escape(section.title)}</h2>"]
    parts += [f"<p>{escape(p)}</p>" for p in section.paragraphs]
    for table in section.tables:
        parts += _table(table, show_title=table.title != section.title)
    for figure in section.figures:
        data = base64.b64encode(figure.png).decode("ascii")
        parts += [
            "<figure>",
            f'<img alt="{escape(figure.title)}" src="data:image/png;base64,{data}">',
            f"<figcaption>{escape(figure.title)}</figcaption>",
            "</figure>",
        ]
    parts.append("</section>")
    return parts


def _table(table: Table, *, show_title: bool) -> list[str]:
    def cell(tag: str, text: str, align: str) -> str:
        css = ' class="right"' if align == "right" else ""
        return f"<{tag}{css}>{escape(text)}</{tag}>"

    parts = [f"<h3>{escape(table.title)}</h3>"] if show_title else []
    parts += ["<table>", "<thead><tr>"]
    parts += [cell("th", c, a) for c, a in zip(table.columns, table.align, strict=True)]
    parts += ["</tr></thead>", "<tbody>"]
    for row in table.rows:
        cells = "".join(cell("td", c, a) for c, a in zip(row, table.align, strict=True))
        parts.append(f"<tr>{cells}</tr>")
    parts += ["</tbody>", "</table>"]
    parts += [f'<p class="note">{escape(note)}</p>' for note in table.notes]
    return parts
