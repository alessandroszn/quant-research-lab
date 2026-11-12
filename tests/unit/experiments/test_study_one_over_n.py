"""Kind ``study_one_over_n`` end to end on synthetic Ken French-format portfolio files."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.cli import main
from qrlab.core.errors import ValidationError
from qrlab.data.ken_french import KEN_FRENCH_DATASETS
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds.study_one_over_n import DATASETS, INPUTS


def _zip(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("file.csv", text.replace("\n", "\r\n").encode("latin-1"))
    return buffer.getvalue()


def _section(title: str, frame: pd.DataFrame, date_format: str, decimals: int = 2) -> str:
    lines = [f"  {title}", "," + ",".join(frame.columns)]
    dates = pd.DatetimeIndex(frame.index).strftime(date_format)
    for when, row in zip(dates, frame.to_numpy(), strict=True):
        lines.append(when + "," + ",".join(f"{v:9.{decimals}f}" for v in row))
    return "\n".join(lines)


def _write_files(
    folder: Path, rng: np.random.Generator, *, months: int = 72, edit: object = None
) -> dict[str, Path]:
    month_ends = pd.date_range("1990-01-31", periods=months, freq="ME")
    days = pd.bdate_range("1990-01-01", month_ends[-1])
    folder.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for daily_name, monthly_name in DATASETS.values():
        columns = list(KEN_FRENCH_DATASETS[INPUTS[monthly_name]].columns)
        n = len(columns)
        common = rng.standard_normal(len(days))
        daily = pd.DataFrame(
            0.04 + 0.6 * common[:, None] + 0.5 * rng.standard_normal((len(days), n)),
            index=days,
            columns=columns,
        ).round(2)
        month = days + pd.offsets.MonthEnd(0)
        monthly = ((1 + daily / 100).groupby(month).prod() - 1) * 100
        firms = pd.DataFrame(
            np.tile(np.arange(10, 10 + 5 * n, 5, dtype=float), (months, 1)),
            index=month_ends,
            columns=columns,
        )
        size = pd.DataFrame(
            np.tile(np.linspace(50.0, 500.0, n), (months, 1)), index=month_ends, columns=columns
        )
        if callable(edit):
            edit(daily, monthly)
        monthly_text = "\n\n".join(
            [
                "  Synthetic portfolio file.\n  Missing data are indicated by -99.99 or -999.",
                _section("Average Value Weighted Returns -- Monthly", monthly, "%Y%m"),
                _section("Average Equal Weighted Returns -- Monthly", monthly * 1.1, "%Y%m"),
                _section("Number of Firms in Portfolios", firms, "%Y%m", 0),
                _section("Average Firm Size", size, "%Y%m"),
            ]
        )
        daily_text = "\n\n".join(
            [
                "  Synthetic portfolio file.",
                _section("Average Value Weighted Returns -- Daily", daily, "%Y%m%d"),
                _section("Average Equal Weighted Returns -- Daily", daily, "%Y%m%d"),
            ]
        )
        for name, text in ((monthly_name, monthly_text), (daily_name, daily_text)):
            path = folder / f"{name}.zip"
            path.write_bytes(_zip(text + "\n\n"))
            paths[name] = path
    rf = pd.DataFrame(
        {"Mkt-RF": 0.5, "SMB": 0.1, "HML": 0.1, "RF": 0.2},
        index=pd.date_range("1989-01-31", periods=months + 24, freq="ME"),
    )
    path = folder / "ff3_monthly.zip"
    path.write_bytes(_zip("Synthetic.\n\n" + _section("", rf, "%Y%m") + "\n\nCopyright\n"))
    paths["ff3_monthly"] = path
    return paths


STRATEGY_LINES = (
    "strategies = [\n"
    '  "ew", "vw", "maxsharpe_sample", "minvar_sample", "minvar_lw", "maxsharpe_bl", '
    '"risk_parity",\n'
    '  "hrp",\n'
    "]"
)

PARAMETERS = """
[parameters]
datasets = ["industries_10", "size_bm_25"]
start = 1990-01-01
end = 1995-12-31
windows = [30, 36]
strategies = [
  "ew", "vw", "maxsharpe_sample", "minvar_sample", "minvar_lw", "maxsharpe_bl", "risk_parity",
  "hrp",
]
costs_bp = [0, 10]
bl_risk_aversion = 2.5
ceq_risk_aversion = 1.0
hac_lags = 3
significance = 0.05
bootstrap = { mean_block_length = 3.0, n_resamples = 100, confidence = 0.9 }
"""


def _config(tmp: Path, paths: dict[str, Path], *, out: str = "run", **replace: str) -> Path:
    inputs = "\n".join(f'{k} = "{v.as_posix()}"' for k, v in paths.items())
    body = PARAMETERS
    for old, new in replace.items():
        assert old in body, old
        body = body.replace(old, new)
    text = (
        '[experiment]\nname = "onen"\nkind = "study_one_over_n"\n'
        'hypothesis = "No optimised strategy beats 1/N after costs"\n'
        f"seed = 11\n\n[inputs]\n{inputs}\n{body}\n"
        f'[output]\ndirectory = "{(tmp / "results" / out).as_posix()}"\n'
    )
    path = tmp / f"onen-{out}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _record(folder: Path) -> dict[str, object]:
    return json.loads((folder / "record.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_kind_inputs() -> None:
    kind = KINDS["study_one_over_n"]
    assert kind.inputs == tuple(INPUTS)
    assert kind.needs_seed


def test_study_runs_end_to_end_through_the_cli(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "data", rng)
    assert main(["run", str(_config(tmp_path, paths))]) == 0
    out = tmp_path / "results" / "run"
    record = _record(out)
    assert record["status"] == "success", record["error"]
    for name in ("performance.csv", "against_1n.csv", "robust_pairs.csv"):
        assert record["outputs"][name]["tag"] == "out_of_sample"  # type: ignore[index]
    perf = pd.read_csv(out / "performance.csv")
    assert len(perf) == 2 * 2 * 2 * 8
    # First decision at month 36 (December 1992); evaluated January 1993 to December 1995.
    assert (perf["n"] == 36).all()
    assert (perf["start"] == "1993-01-31").all()
    ew = perf[perf["strategy"] == "ew"].set_index(["dataset", "window", "cost_per_unit"])
    assert (ew["turnover"] > 0).all()
    gross = ew.xs(0.0, level="cost_per_unit")["mean"]
    net = ew.xs(0.001, level="cost_per_unit")["mean"]
    assert (net < gross).all()
    tests = pd.read_csv(out / "against_1n.csv")
    assert len(tests) == 2 * 2 * 2 * 7
    assert "ew" not in set(tests["strategy"])
    pairs = pd.read_csv(out / "robust_pairs.csv")
    assert len(pairs) == 2 * 2 * 2 * 2
    scalars = record["scalars"]
    assert scalars["dsr_trials"]["value"] == 64.0  # type: ignore[index]
    assert scalars["configurations_tried"]["value"] == 1.0  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Net performance and tests against 1/N" in html
    assert "Robust estimation (H2)" in html
    assert "not investment advice" in html


def test_smaller_run_without_pairs(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "data", rng)
    config = _config(
        tmp_path,
        paths,
        **{
            'datasets = ["industries_10", "size_bm_25"]': 'datasets = ["industries_10"]',
            STRATEGY_LINES: 'strategies = ["ew", "hrp"]',
            "windows = [30, 36]": "windows = [36]",
            "costs_bp = [0, 10]": "costs_bp = [0]",
        },
    )
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    assert "robust_pairs.csv" not in result.record["outputs"]
    assert "robust_better_holm" not in result.record["scalars"]


def test_data_problems_fail_the_run(tmp_path: Path, rng: np.random.Generator) -> None:
    def gap(daily: pd.DataFrame, monthly: pd.DataFrame) -> None:
        monthly.iloc[20, 0] = -99.99

    paths = _write_files(tmp_path / "gap", rng, edit=gap)
    result = run_experiment(_config(tmp_path, paths, out="gap"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "missing values inside the sample window" in str(result.record["error"])

    paths = _write_files(tmp_path / "short", rng)
    short = _config(tmp_path, paths, out="short", **{"end = 1995-12-31": "end = 1992-12-31"})
    result = run_experiment(short, kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "fewer months than the longest window" in str(result.record["error"])

    late = _config(
        tmp_path,
        paths,
        out="late",
        **{"start = 1990-01-01": "start = 2030-01-01", "end = 1995-12-31": "end = 2031-12-31"},
    )
    result = run_experiment(late, kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "no data between" in str(result.record["error"])


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('datasets = ["industries_10", "size_bm_25"]', 'datasets = ["x"]', "unknown datasets"),
        ('  "ew", "vw",', '  "zz", "vw",', "unknown strategies"),
        ('  "ew", "vw",', '  "vw",', "include the 1/N"),
        ("end = 1995-12-31", "end = 1989-12-31", "start must be before end"),
        ("windows = [30, 36]", "windows = [30.5]", "whole numbers"),
        ("windows = [30, 36]", "windows = [1]", "whole numbers"),
        ("costs_bp = [0, 10]", "costs_bp = [-1]", "costs_bp must be >= 0"),
        ("bl_risk_aversion = 2.5", "bl_risk_aversion = 0", "bl_risk_aversion must be positive"),
        ("significance = 0.05", "significance = 2.0", "significance must be in"),
    ],
)
def test_parameters_are_validated(tmp_path: Path, old: str, new: str, message: str) -> None:
    paths = {k: tmp_path / f"{k}.zip" for k in INPUTS}
    for path in paths.values():
        path.write_bytes(b"x")
    with pytest.raises(ValidationError, match=message):
        validate_experiment(_config(tmp_path, paths, **{old: new}), kinds=KINDS)
