"""Kind ``study_volatility_managed`` end to end on synthetic Ken French-format files."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.cli import main
from qrlab.core.errors import ValidationError
from qrlab.data.ken_french import ken_french_url
from qrlab.data.provenance import Provenance
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds.study_volatility_managed import FACTORS, INPUTS

COLUMNS = {
    "ff3": ("Mkt-RF", "SMB", "HML", "RF"),
    "ff5": ("Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"),
    "mom": ("Mom",),
}


def _zip(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("file.csv", text.replace("\n", "\r\n").encode("latin-1"))
    return buffer.getvalue()


def _section(frame: pd.DataFrame, date_format: str) -> str:
    lines = ["," + ",".join(frame.columns)]
    dates = pd.DatetimeIndex(frame.index).strftime(date_format)
    for when, row in zip(dates, frame.to_numpy(), strict=True):
        lines.append(when + "," + ",".join(f"{v:8.2f}" for v in row))
    return "\n".join(lines)


def _write_files(
    folder: Path, rng: np.random.Generator, *, months: int = 216, edit: object = None
) -> dict[str, Path]:
    """Synthetic factor files: persistent monthly volatility, constant mean (percent)."""
    month_ends = pd.date_range("1990-01-31", periods=months, freq="ME")
    days = pd.bdate_range("1990-01-01", month_ends[-1])
    daily = {}
    for column in sorted({c for cols in COLUMNS.values() for c in cols}):
        state = np.zeros(len(month_ends))
        for i in range(1, len(month_ends)):
            state[i] = 0.9 * state[i - 1] + 0.4 * rng.standard_normal()
        vol = (
            pd.Series(np.exp(state), index=month_ends)
            .reindex(days + pd.offsets.MonthEnd(0))
            .to_numpy()
        )
        daily[column] = 0.03 + 0.8 * vol * rng.standard_normal(len(days))
    daily_frame = pd.DataFrame(daily, index=days).round(2)
    monthly_frame = daily_frame.groupby(days + pd.offsets.MonthEnd(0)).sum()
    if callable(edit):
        edit(daily_frame, monthly_frame)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for family, columns in COLUMNS.items():
        cols = list(columns)
        for suffix, frame, fmt in (
            ("daily", daily_frame, "%Y%m%d"),
            ("monthly", monthly_frame, "%Y%m"),
        ):
            text = f"Synthetic test file.\n\n{_section(frame[cols], fmt)}\n\nCopyright test\n"
            path = folder / f"{family}_{suffix}.zip"
            path.write_bytes(_zip(text))
            paths[f"{family}_{suffix}"] = path
    return paths


PARAMETERS = """
[parameters]
factors = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
start = 1990-01-01
end = 2007-12-31
demean_daily = false
hac_lags = 6
burn_in_months = 60
leverage_caps = [5.0, inf]
costs_bp = [0, 10]
significance = 0.05
bootstrap = { mean_block_length = 6.0, n_resamples = 200, confidence = 0.95 }
"""


def _config(
    tmp: Path, paths: dict[str, Path], *, name: str = "vm", out: str = "run", **replace: str
) -> Path:
    inputs = "\n".join(f'{k} = "{v.as_posix()}"' for k, v in paths.items())
    body = PARAMETERS
    for old, new in replace.items():
        assert old in body, old
        body = body.replace(old, new)
    text = (
        f'[experiment]\nname = "{name}"\nkind = "study_volatility_managed"\n'
        'hypothesis = "Real-time volatility management does not raise net Sharpe ratios"\n'
        f"seed = 7\n\n[inputs]\n{inputs}\n{body}\n"
        f'[output]\ndirectory = "{(tmp / "results" / out).as_posix()}"\n'
    )
    path = tmp / f"{name}-{out}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _record(folder: Path) -> dict[str, object]:
    return json.loads((folder / "record.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_kind_is_registered_with_the_six_files() -> None:
    kind = KINDS["study_volatility_managed"]
    assert kind.inputs == tuple(INPUTS)
    assert kind.needs_seed
    assert set(FACTORS) == {"Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"}


def test_study_runs_end_to_end_through_the_cli(
    tmp_path: Path, rng: np.random.Generator, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _write_files(tmp_path / "data", rng)
    config = _config(tmp_path, paths)
    assert main(["run", str(config)]) == 0
    out = tmp_path / "results" / "run"
    record = _record(out)
    assert record["status"] == "success", record["error"]
    outputs = record["outputs"]
    assert outputs["in_sample.csv"]["tag"] == "in_sample"  # type: ignore[index]
    assert outputs["out_of_sample.csv"]["tag"] == "out_of_sample"  # type: ignore[index]
    assert outputs["weights.csv"]["tag"] == "out_of_sample"  # type: ignore[index]
    in_sample = pd.read_csv(out / "in_sample.csv", index_col="factor")
    assert list(in_sample.index) == list(FACTORS)
    # Months 1990-02 to 2007-12: the first month has no lagged variance.
    assert (in_sample["n"] == 215).all()
    oos = pd.read_csv(out / "out_of_sample.csv")
    assert len(oos) == 6 * 2 * 2
    assert (oos["n"] == 215 - 60).all()
    assert set(oos["cost_per_unit"]) == {0.0, 0.001}
    weights = pd.read_csv(out / "weights.csv", index_col=0)
    assert weights.filter(like="cap 5").to_numpy().max() <= 5.0
    scalars = record["scalars"]
    assert scalars["configurations_tried"] == {"value": 1.0, "tag": "descriptive"}  # type: ignore[index]
    assert scalars["dsr_trials"]["value"] == 24.0  # type: ignore[index]
    assert 0.0 <= scalars["dsr_probability"]["value"] <= 1.0  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Spanning regressions (in sample)" in html
    assert "no cap" in html
    assert "cap 5.0x" in html
    assert "not investment advice" in html
    assert "file:ff3_daily.zip" in html

    # A second configuration counts as a second trial; rerunning the same one does not.
    second = _config(tmp_path, paths, out="run2", **{"[5.0, inf]": "[2.0]"})
    result = run_experiment(second, kinds=KINDS, overwrite=False)
    assert result.record["scalars"]["configurations_tried"]["value"] == 2.0
    assert result.record["scalars"]["dsr_trials"]["value"] == 6 * 2 * 2
    again = run_experiment(config, kinds=KINDS, overwrite=True)
    assert again.record["scalars"]["configurations_tried"]["value"] == 2.0
    # Same seed and inputs: identical tables.
    assert again.record["outputs"]["out_of_sample.csv"] == record["outputs"]["out_of_sample.csv"]  # type: ignore[index]


def test_single_variant_has_no_deflated_sharpe(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "data", rng)
    config = _config(
        tmp_path,
        paths,
        **{
            '["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]': '["Mkt-RF"]',
            "[5.0, inf]": "[inf]",
            "[0, 10]": "[0]",
            "demean_daily = false": "demean_daily = true",
        },
    )
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    assert "dsr_probability" not in result.record["scalars"]
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    assert "Deflated Sharpe ratio not computed" in html


def test_raw_store_sidecar_is_used_and_checked(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "data", rng)
    path = paths["ff3_daily"]
    content = path.read_bytes()

    def sidecar(dataset: str, sha: str) -> None:
        provenance = Provenance(
            source="ken_french",
            dataset=dataset,
            url=ken_french_url(dataset),
            retrieved_at=datetime(2026, 11, 12, tzinfo=UTC),
            sha256=sha,
            size_bytes=len(content),
            terms="test",
        )
        path.with_name(path.name + ".provenance.json").write_text(
            provenance.to_json(), encoding="utf-8"
        )

    good = hashlib.sha256(content).hexdigest()
    sidecar(INPUTS["ff3_daily"], good)
    result = run_experiment(_config(tmp_path, paths, out="a"), kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    assert ken_french_url(INPUTS["ff3_daily"]) in html
    assert "retrieved 2026-11-12" in html

    sidecar(INPUTS["ff3_daily"], "0" * 64)
    result = run_experiment(_config(tmp_path, paths, out="b"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "SHA-256 differs" in str(result.record["error"])

    sidecar(INPUTS["ff5_daily"], good)
    result = run_experiment(_config(tmp_path, paths, out="c"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "expected ken_french/F-F_Research_Data_Factors_daily" in str(result.record["error"])


def test_leading_missing_values_are_trimmed_inner_ones_fail(
    tmp_path: Path, rng: np.random.Generator
) -> None:
    def leading(daily: pd.DataFrame, monthly: pd.DataFrame) -> None:
        daily.loc[:"1990-03-31", "RMW"] = -99.99
        monthly.loc[:"1990-03-31", "RMW"] = -99.99

    paths = _write_files(tmp_path / "lead", rng, edit=leading)
    result = run_experiment(_config(tmp_path, paths, out="lead"), kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    in_sample = pd.read_csv(result.output_dir / "in_sample.csv", index_col="factor")
    assert in_sample.loc["RMW", "start"] == "1990-05-31"
    assert in_sample.loc["Mkt-RF", "start"] == "1990-02-28"

    def inner(daily: pd.DataFrame, monthly: pd.DataFrame) -> None:
        monthly.loc["1995-06-30", "CMA"] = -99.99

    paths = _write_files(tmp_path / "inner", rng, edit=inner)
    result = run_experiment(_config(tmp_path, paths, out="inner"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "CMA monthly: missing values inside the sample window" in str(result.record["error"])

    paths = _write_files(tmp_path / "late", rng)
    late = _config(
        tmp_path,
        paths,
        out="late",
        **{"start = 1990-01-01": "start = 2030-01-01", "end = 2007-12-31": "end = 2031-12-31"},
    )
    result = run_experiment(late, kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "no data between" in str(result.record["error"])


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('"Mom"]', '"Momentum"]', "unknown factors"),
        ('["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]', '["SMB", "SMB"]', "duplicates"),
        ('["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]', "[]", "non-empty list of names"),
        ('["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]', "[1]", "non-empty list of names"),
        ("end = 2007-12-31", "end = 1989-12-31", "start must be before end"),
        ("[5.0, inf]", "[0.0]", "leverage_caps must be positive"),
        ("[5.0, inf]", "[5, 5.0]", "leverage_caps has duplicates"),
        ("[5.0, inf]", '["5"]', "leverage_caps must contain numbers or inf"),
        ("[5.0, inf]", "[nan]", "leverage_caps must contain numbers or inf"),
        ("[5.0, inf]", "5.0", "non-empty list of numbers"),
        ("[0, 10]", "[inf]", "costs_bp must contain numbers"),
        ("[0, 10]", "[-1]", "costs_bp must be >= 0"),
        ("significance = 0.05", "significance = 1.5", "significance must be in"),
        ("burn_in_months = 60", "burn_in_months = 1", "burn_in_months"),
        ("n_resamples = 200", "n_resamples = 20", "n_resamples"),
    ],
)
def test_parameters_are_validated(
    tmp_path: Path, rng: np.random.Generator, old: str, new: str, message: str
) -> None:
    paths = {k: tmp_path / f"{k}.zip" for k in INPUTS}
    for path in paths.values():
        path.write_bytes(b"x")
    with pytest.raises(ValidationError, match=message):
        validate_experiment(_config(tmp_path, paths, **{old: new}), kinds=KINDS)
