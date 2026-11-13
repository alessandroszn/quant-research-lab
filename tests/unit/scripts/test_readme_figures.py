"""README figures drawn from study tables (design note 6.3c), on synthetic tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import readme_figures

PNG = b"\x89PNG\r\n\x1a\n"


def _factor_zoo(folder: Path) -> Path:
    folder.mkdir(parents=True)
    pd.DataFrame(
        {
            "beta_post_sample": [-0.0026],
            "beta_post_publication": [-0.0043],
            "se_post_sample": [0.0007],
            "se_post_publication": [0.0006],
            "in_sample_mean": [0.0074],
            "n_predictors": [160],
        }
    ).to_csv(folder / "decay.csv")
    return folder


def _one_over_n(folder: Path) -> Path:
    folder.mkdir(parents=True)
    rows = [
        ["industries_10", 60, 0.005, s, sharpe, "1973-07-31", "2004-12-31"]
        for s, sharpe in [("ew", 0.47), ("vw", 0.40), ("hrp", 0.49), ("new_one", 0.3)]
    ]
    columns = ["dataset", "window", "cost_per_unit", "strategy", "sharpe", "start", "end"]
    pd.DataFrame(rows, columns=columns).to_csv(folder / "performance.csv")
    return folder


def test_figures_are_png_and_deterministic(tmp_path: Path) -> None:
    zoo = _factor_zoo(tmp_path / "factor-zoo" / "clear")
    first = readme_figures.factor_zoo_figure(zoo)
    assert first.startswith(PNG)
    assert first == readme_figures.factor_zoo_figure(zoo)
    one = _one_over_n(tmp_path / "one-over-n" / "paper")
    picture = readme_figures.one_over_n_figure(one, dataset="industries_10", window=60, cost=0.005)
    assert picture.startswith(PNG)
    assert picture == readme_figures.one_over_n_figure(
        one, dataset="industries_10", window=60, cost=0.005
    )


def test_a_missing_selection_raises(tmp_path: Path) -> None:
    one = _one_over_n(tmp_path / "one")
    with pytest.raises(ValueError, match="no rows"):
        readme_figures.one_over_n_figure(one, dataset="industries_10", window=120, cost=0.005)


def test_command_line(tmp_path: Path) -> None:
    _factor_zoo(tmp_path / "studies" / "factor-zoo" / "clear")
    _one_over_n(tmp_path / "studies" / "one-over-n" / "paper")
    out = tmp_path / "out"
    assert readme_figures.main([str(tmp_path / "studies"), str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == sorted(readme_figures.FIGURES)
    assert readme_figures.main([]) == 2
