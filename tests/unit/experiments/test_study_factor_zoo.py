"""Kind ``study_factor_zoo`` end to end on synthetic OSAP-format files."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.cli import main
from qrlab.core.errors import ValidationError
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds.study_factor_zoo import INPUTS


def _write_files(folder: Path, rng: np.random.Generator, *, gap: bool = False) -> dict[str, Path]:
    """Twelve predictors, 1970-2020, returns in percent that halve after publication."""
    months = pd.date_range("1970-01-31", "2020-12-31", freq="ME")
    doc_rows: list[dict[str, object]] = []
    columns: dict[str, pd.Series] = {}
    for i in range(12):
        start, end, year = 1970 + i, 1990 + i, 1995 + i
        name = f"P{i:02d}"
        years = months.year
        mean = np.where(years <= end, 0.8, np.where(years <= year, 0.6, 0.4))
        series = mean + 3.0 * rng.standard_normal(len(months))
        values = pd.Series(series, index=months)
        if i % 2:  # odd predictors start in 1972: series of different lengths
            values.loc[months.year < 1972] = np.nan
        columns[name] = values.round(4)
        doc_rows.append(
            {
                "Acronym": name,
                "Cat.Signal": "Predictor",
                "Predictability in OP": "1_clear" if i < 9 else "2_likely",
                "Authors": f"Author {i}",
                "Year": year,
                "Journal": "JF",
                "LongDescription": f"Predictor {i}",
                "Cat.Data": "Accounting",
                "SampleStartYear": start,
                "SampleEndYear": end,
                "Sign": 1.0,
            }
        )
    doc_rows.append(
        {
            "Acronym": "Placebo",
            "Cat.Signal": "Placebo",
            "Predictability in OP": "4_not",
            "Authors": "x",
            "Year": None,
            "Journal": "x",
            "LongDescription": "x",
            "Cat.Data": "x",
            "SampleStartYear": None,
            "SampleEndYear": None,
            "Sign": 1.0,
        }
    )
    wide = pd.DataFrame(columns, index=months)
    if gap:
        wide.iloc[100:110, 0] = np.nan
    wide.insert(0, "date", months.date)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {
        "ls_returns": folder / "PredictorLSretWide.parquet",
        "signal_doc": folder / "SignalDoc.csv",
    }
    wide.to_parquet(paths["ls_returns"], index=False)
    pd.DataFrame(doc_rows).to_csv(paths["signal_doc"], index=False)
    return paths


PARAMETERS = """
[parameters]
categories = ["1_clear"]
end = 2020-12-31
hac_lags = 6
min_months = 12
hlz_threshold = 3.0
significance = 0.05
"""


def _config(tmp: Path, paths: dict[str, Path], *, out: str = "run", **replace: str) -> Path:
    inputs = "\n".join(f'{k} = "{v.as_posix()}"' for k, v in paths.items())
    body = PARAMETERS
    for old, new in replace.items():
        assert old in body, old
        body = body.replace(old, new)
    text = (
        '[experiment]\nname = "zoo"\nkind = "study_factor_zoo"\n'
        'hypothesis = "Returns fall after the sample and after publication"\n\n'
        f"[inputs]\n{inputs}\n{body}\n"
        f'[output]\ndirectory = "{(tmp / "results" / out).as_posix()}"\n'
    )
    path = tmp / f"zoo-{out}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _record(folder: Path) -> dict[str, object]:
    return json.loads((folder / "record.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_kind_inputs() -> None:
    kind = KINDS["study_factor_zoo"]
    assert kind.inputs == tuple(INPUTS)
    assert not kind.needs_seed


def test_study_runs_end_to_end_through_the_cli(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "data", rng)
    assert main(["run", str(_config(tmp_path, paths))]) == 0
    out = tmp_path / "results" / "run"
    record = _record(out)
    assert record["status"] == "success", record["error"]
    outputs = record["outputs"]
    assert outputs["in_sample_tests.csv"]["tag"] == "in_sample"  # type: ignore[index]
    assert outputs["in_sample_counts.csv"]["tag"] == "in_sample"  # type: ignore[index]
    assert outputs["composite_in_sample.csv"]["tag"] == "in_sample"  # type: ignore[index]
    for name in (
        "decay.csv",
        "post_publication_counts.csv",
        "by_predictor.csv",
        "composites_later.csv",
    ):
        assert outputs[name]["tag"] == "out_of_sample"  # type: ignore[index]
    tests = pd.read_csv(out / "in_sample_tests.csv", index_col="predictor")
    assert len(tests) == 9  # the clear predictors only
    decay = pd.read_csv(out / "decay.csv").iloc[0]
    # Simulated means 0.8 % in sample, 0.6 % post-sample, 0.4 % post-publication.
    assert decay["beta_post_publication"] < decay["beta_post_sample"] < 0
    assert decay["n_predictors"] == 9
    scalars = record["scalars"]
    assert scalars["predictors"]["value"] == 9.0  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "McLean-Pontiff decay (H2)" in html
    assert "CC BY 4.0" in html
    assert "not investment advice" in html

    broad = _config(tmp_path, paths, out="broad", **{'["1_clear"]': '["1_clear", "2_likely"]'})
    result = run_experiment(broad, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    assert result.record["scalars"]["predictors"]["value"] == 12.0
    assert result.record["scalars"]["configurations_tried"]["value"] == 2.0


def test_gaps_and_empty_universe_fail(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "gap", rng, gap=True)
    result = run_experiment(_config(tmp_path, paths, out="gap"), kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    # P00 has 10 of 612 months missing (1.6 %): excluded and listed, not a failure.
    assert result.record["scalars"]["excluded_for_gaps"]["value"] == 1.0
    assert result.record["scalars"]["predictors"]["value"] == 8.0
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    assert "P00 (1.6%)" in html

    paths = _write_files(tmp_path / "data", rng)
    empty = _config(tmp_path, paths, out="empty", **{'["1_clear"]': '["9_none"]'})
    result = run_experiment(empty, kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "no predictors in categories" in str(result.record["error"])


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("significance = 0.05", "significance = 0", "significance must be in"),
        ("hlz_threshold = 3.0", "hlz_threshold = -1.0", "hlz_threshold must be positive"),
        ("min_months = 12", "min_months = 2", "min_months"),
        ('categories = ["1_clear"]', "categories = []", "non-empty list of names"),
    ],
)
def test_parameters_are_validated(tmp_path: Path, old: str, new: str, message: str) -> None:
    paths = {k: tmp_path / f"{k}.bin" for k in INPUTS}
    for path in paths.values():
        path.write_bytes(b"x")
    with pytest.raises(ValidationError, match=message):
        validate_experiment(_config(tmp_path, paths, **{old: new}), kinds=KINDS)


def test_inconsistent_inputs_fail(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "extra", rng)
    doc = pd.read_csv(paths["signal_doc"])
    extra = doc.iloc[[0]].assign(Acronym="NotInReturns")
    pd.concat([doc, extra]).to_csv(paths["signal_doc"], index=False)
    result = run_experiment(_config(tmp_path, paths, out="extra"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "no returns for predictors ['NotInReturns']" in str(result.record["error"])

    paths = _write_files(tmp_path / "holes", rng)
    wide = pd.read_parquet(paths["ls_returns"])
    wide.iloc[200:220, 1:] = np.nan  # 20 months inside every series
    wide.to_parquet(paths["ls_returns"], index=False)
    result = run_experiment(_config(tmp_path, paths, out="holes"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "every selected predictor has too many missing months" in str(result.record["error"])
