"""Reports, tables and figures.

Reports only format results of tested functions; they compute nothing new. Every report states
its data dates, provenance and assumptions, lists carried-forward values and warnings in a
visible box, and ends with a "not investment advice" notice. HTML output is a single
self-contained file (no external resources) and deterministic for identical inputs.

Modules:

- ``formatting`` and ``labels``: Italian and English number styles and texts.
- ``tables`` and ``figures``: formatted tables and deterministic PNG figures (Agg canvas).
- ``html``: :class:`Report` and :func:`render_html` / :func:`write_report`.
- ``portfolio_report``: :func:`build_portfolio_report`.

Planned: experiment records (phase 5.2).
"""

from qrlab.reporting.figures import AxisFormat, line_figure
from qrlab.reporting.formatting import (
    EN,
    IT,
    Language,
    NumberStyle,
    escape,
    format_date,
    format_money,
    format_number,
    format_percent,
    format_significant,
    style_for,
)
from qrlab.reporting.html import Figure, Report, Section, render_html, write_report
from qrlab.reporting.labels import LABELS, label
from qrlab.reporting.portfolio_report import RiskFreeSummary, build_portfolio_report
from qrlab.reporting.tables import Table

__all__ = [
    "EN",
    "IT",
    "LABELS",
    "AxisFormat",
    "Figure",
    "Language",
    "NumberStyle",
    "Report",
    "RiskFreeSummary",
    "Section",
    "Table",
    "build_portfolio_report",
    "escape",
    "format_date",
    "format_money",
    "format_number",
    "format_percent",
    "format_significant",
    "label",
    "line_figure",
    "render_html",
    "style_for",
    "write_report",
]
