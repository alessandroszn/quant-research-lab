"""Draw the README figures from the study results (design note 6.3c).

Usage, from the repository root, after running the study configs:
``uv run python scripts/readme_figures.py results/studies docs/_static/readme``

The figures are drawn only from the tables the studies wrote, so they show exactly the
published numbers. The PNG files are deterministic: the same tables give the same bytes.
"""

from __future__ import annotations

import io
import sys
from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")  # before pyplot is imported: no display is ever needed
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure

__all__ = ["FIGURES", "factor_zoo_figure", "main", "one_over_n_figure"]

_PHASES = {
    "in_sample": "In sample",
    "post_sample": "After the sample",
    "post_publication": "After publication",
}
_DATASETS = {"industries_10": "10 industries", "size_bm_25": "25 size/value portfolios"}
_STRATEGIES = {
    "ew": "1/N",
    "vw": "Value weights",
    "minvar_sample": "Min. variance",
    "minvar_lw": "Min. variance (LW)",
    "maxsharpe_sample": "Max. Sharpe",
    "maxsharpe_bl": "Max. Sharpe (BL)",
    "risk_parity": "Risk parity",
    "hrp": "HRP",
}


def _png(figure: Figure) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=110, metadata={"Software": None})
    plt.close(figure)
    return buffer.getvalue()


def factor_zoo_figure(folder: Path) -> bytes:
    """Draw returns after the sample and after publication relative to in sample (study 3).

    The bars are the panel regression's decay estimates (``decay.csv``): the same predictors
    compared with themselves, which is the result the report states. Composite averages are
    not used, because they mix different predictors and periods.
    """
    row = pd.read_csv(folder / "decay.csv").iloc[0]
    mean = float(row["in_sample_mean"])
    levels = [100.0]
    errors = [0.0]
    for phase in ("post_sample", "post_publication"):
        levels.append(100 * (1 + float(row[f"beta_{phase}"]) / mean))
        errors.append(100 * 1.96 * float(row[f"se_{phase}"]) / abs(mean))
    figure, axis = plt.subplots(figsize=(6.4, 3.4))
    bars = axis.bar(
        list(_PHASES.values()),
        levels,
        yerr=errors,
        capsize=4,
        color=["#8c8c8c", "#4c72b0", "#4c72b0"],
    )
    for bar, level in zip(bars, levels, strict=True):
        axis.annotate(
            f"{level:.0f}",
            (bar.get_x() + bar.get_width() / 2, 4),
            ha="center",
            va="bottom",
            fontsize=9,
            color="white",
        )
    axis.set_ylabel("Mean return (in sample = 100)")
    axis.set_title(
        f"Study 3: {int(row['n_predictors'])} published predictors, with 95 % intervals",
        fontsize=10,
    )
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    return _png(figure)


def one_over_n_figure(folder: Path, *, dataset: str, window: int, cost: float) -> bytes:
    """Bars of the out-of-sample Sharpe ratio per strategy (study 2), 1/N highlighted."""
    table = pd.read_csv(folder / "performance.csv")
    rows = table[
        (table["dataset"] == dataset)
        & (table["window"] == window)
        & (table["cost_per_unit"] == cost)
    ].set_index("strategy")
    if rows.empty:
        raise ValueError(f"no rows for {dataset}, window {window}, cost {cost}")
    rows = rows.loc[[s for s in _STRATEGIES if s in rows.index]]
    figure, axis = plt.subplots(figsize=(6.4, 3.6))
    colours = ["#c44e52" if s == "ew" else "#8c8c8c" for s in rows.index]
    axis.barh([_STRATEGIES[s] for s in rows.index], rows["sharpe"], color=colours)
    axis.invert_yaxis()
    axis.set_xlabel("Out-of-sample Sharpe ratio (annual)")
    start, end = str(rows["start"].iloc[0])[:4], str(rows["end"].iloc[0])[:4]
    axis.set_title(
        f"Study 2, {_DATASETS.get(dataset, dataset)}: {window}-month window, "
        f"{cost * 1e4:.0f} bp costs, {start}-{end}",
        fontsize=10,
    )
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    return _png(figure)


FIGURES = ("factor-zoo.png", "one-over-n.png")


def main(argv: Sequence[str] | None = None) -> int:
    """Write the README figures from the results folder into the output folder."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: readme_figures.py RESULTS_STUDIES OUTPUT_FOLDER", file=sys.stderr)
        return 2
    results, out = Path(args[0]), Path(args[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / FIGURES[0]).write_bytes(factor_zoo_figure(results / "factor-zoo" / "clear"))
    (out / FIGURES[1]).write_bytes(
        one_over_n_figure(
            results / "one-over-n" / "paper", dataset="industries_10", window=60, cost=0.005
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - run by hand after the studies
    raise SystemExit(main())
