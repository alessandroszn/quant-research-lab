"""The PDF export of a report (design note 12.4): the print adapter and the export."""

from __future__ import annotations

import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from qrlab.experiments import run_experiment
from qrlab.experiments.kinds import KINDS
from qrlab_app.pdf import (
    PRINT_STYLE,
    WIDE_TABLE,
    adapt_html,
    export_pdf,
    is_wide,
    max_columns,
    text_width,
)

ROOT = Path(__file__).parents[3]


def _table(columns: int) -> str:
    cells = "".join(f"<td>c{n}</td>" for n in range(columns))
    return f"<table><tr>{cells}</tr></table>"


def test_columns_and_orientation() -> None:
    assert max_columns("<p>no table</p>") == 0
    assert max_columns(_table(3) + _table(7)) == 7
    assert max_columns("<table><tr><th>a</th><td>b</td></tr><tr><td>1</td></tr></table>") == 2
    assert not is_wide(_table(WIDE_TABLE))
    assert is_wide(_table(WIDE_TABLE + 1))


def test_text_width_by_hand() -> None:
    assert text_width(landscape=False) == 642  # (210 - 2 x 20) mm / 25.4 x 96 = 642.5
    assert text_width(landscape=True) == 971  # (297 - 2 x 20) mm / 25.4 x 96 = 971.3


def test_the_adapter_changes_the_layout_only() -> None:
    html = (
        "<html><head><style>body { margin: 2rem; }</style></head><body class='x'>"
        "<figure><img src='data:image/png;base64,AAAA' alt='v'>"
        "<figcaption>Value</figcaption></figure>"
        "<table class='t'><tr><td class='right'>1,00 EUR</td></tr></table></body></html>"
    )
    adapted = adapt_html(html, image_width=600, header="Print of a & b")
    assert "<style" not in adapted  # the browser style sheet goes; PRINT_STYLE replaces it
    assert "<figure" not in adapted
    assert "<figcaption" not in adapted
    assert '<img width="600" src=' in adapted
    assert '<table cellpadding="3" cellspacing="0" class=' in adapted
    assert adapted.index("<body class='x'>") < adapted.index("Print of a &amp; b")
    assert adapted.index("Print of a &amp; b") < adapted.index("<img")
    words = re.sub(r"<[^>]+>", " ", adapted).split()
    assert words == ["Print", "of", "a", "&amp;", "b", "Value", "1,00", "EUR"]
    assert adapt_html("<p>x</p>", image_width=1, header="h") == '<p class="note">h</p><p>x</p>'
    assert "td.right" in PRINT_STYLE


class _Cells(HTMLParser):
    """The text of every table cell of an HTML file."""

    def __init__(self) -> None:
        super().__init__()
        self.cells: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("td", "th"):
            self._depth += 1
            self.cells.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth:
            self.cells[-1] += data


def _report(name: str, tmp: Path) -> Path:
    text = (ROOT / "configs/experiments" / name).read_text(encoding="utf-8")
    text = text.replace('"../../', f'"{ROOT.as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    directory = tomllib.loads(text)["output"]["directory"]
    text = text.replace(f'directory = "{directory}"', f'directory = "{(tmp / "out").as_posix()}"')
    config = tmp / name
    config.write_text(text, encoding="utf-8")
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    return result.output_dir / "report.html"


@pytest.mark.parametrize(
    "name", ["example_portfolio_report.toml", "example_portfolio_report_full.toml"]
)
def test_every_example_report_prints_with_all_its_cells(
    qapp: QApplication, tmp_path: Path, name: str
) -> None:
    report = _report(name, tmp_path)
    target = tmp_path / "exports" / "report.pdf"
    document = export_pdf(report, target, header="Print of the report.", title="example")
    data = target.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", data)) >= 2
    text = " ".join(document.toPlainText().split())
    parser = _Cells()
    parser.feed(report.read_text(encoding="utf-8"))
    cells = [" ".join(c.split()) for c in parser.cells if c.strip()]
    assert cells
    missing = [c for c in cells if c not in text]
    assert missing == []
    assert text.startswith("Print of the report.")


def test_what_cannot_be_exported(qapp: QApplication, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        export_pdf(tmp_path / "gone.html", tmp_path / "a.pdf", header="h", title="t")
    report = tmp_path / "report.html"
    report.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")
    folder = tmp_path / "a folder"
    folder.mkdir()
    with pytest.raises(OSError, match="could not be written"):
        export_pdf(report, folder, header="h", title="t")


def test_a_study_style_report_prints_with_all_its_cells(qapp: QApplication, tmp_path: Path) -> None:
    """The studies render with the same pieces: sections, wide tables, notes and figures."""
    import pandas as pd

    from qrlab.reporting import (
        AxisFormat,
        Figure,
        Language,
        Report,
        Section,
        Table,
        line_figure,
        render_html,
    )
    from qrlab.reporting.formatting import style_for

    columns = tuple(f"Policy {n}" for n in range(9))
    rows = tuple(tuple(f"{r}.{c} %" for c in range(9)) for r in range(12))
    series = pd.Series([1.0, 1.1, 1.05], index=pd.date_range("2020-01-31", periods=3, freq="ME"))
    png = line_figure(
        [("wealth", series)], title="Wealth", y_label="", axis=AxisFormat.NUMBER,
        style=style_for(Language.EN),
    )  # fmt: skip
    report = Report(
        title="A study",
        language=Language.EN,
        facts=(("Sample", "1990-2025"),),
        warnings=("A null result is a result.",),
        sections=(
            Section(
                "Results",
                ("Paired differences against the reference policy.",),
                (Table("Sharpe ratios", columns, rows, ("right",) * 9, ("Net of costs.",)),),
                (Figure("Wealth", png),),
            ),
        ),
        footer=("Analytics, not investment advice.",),
    )
    path = tmp_path / "report.html"
    path.write_text(render_html(report), encoding="utf-8")
    assert is_wide(path.read_text(encoding="utf-8"))
    document = export_pdf(path, tmp_path / "study.pdf", header="Print.", title="study")
    text = " ".join(document.toPlainText().split())
    for row in rows:
        for cell in row:
            assert cell in text
    assert "A null result is a result." in text
