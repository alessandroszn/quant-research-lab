"""The kinds guide is generated from the schemas and committed as generated (design 12.1)."""

from __future__ import annotations

from pathlib import Path

import kinds_guide
import pytest

ROOT = Path(__file__).parents[3]


def test_the_committed_guide_is_the_generated_one() -> None:
    committed = (ROOT / "docs/guides/kinds.md").read_text(encoding="utf-8")
    assert committed == kinds_guide.guide(), "run: uv run python scripts/kinds_guide.py"


def test_the_guide_lists_nested_keys_and_variants() -> None:
    text = kinds_guide.guide()
    assert "| `risk.backtest.window` |" in text
    assert "| `tax.country` | choice | yes |" in text
    assert "`strategy(name = trend).lookback`" in text
    assert text.count("### `") == 10


def test_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(kinds_guide, "OUTPUT", tmp_path / "kinds.md")
    monkeypatch.setattr(kinds_guide, "ROOT", tmp_path)
    assert kinds_guide.main([]) == 0
    assert (tmp_path / "kinds.md").read_text(encoding="utf-8") == kinds_guide.guide()
    assert "wrote kinds.md" in capsys.readouterr().out
    assert kinds_guide.main(["extra"]) == 2


def test_a_kind_without_a_section_or_schema_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from qrlab.experiments.kinds import KINDS

    kinds = dict(KINDS)
    monkeypatch.setattr(
        kinds_guide, "KINDS", kinds | {"new": replace(kinds["backtest"], name="new")}
    )
    with pytest.raises(ValueError, match="kinds without a section"):
        kinds_guide.guide()
    monkeypatch.setattr(
        kinds_guide, "KINDS", kinds | {"backtest": replace(kinds["backtest"], schema=None)}
    )
    with pytest.raises(ValueError, match="has no schema"):
        kinds_guide.guide()
