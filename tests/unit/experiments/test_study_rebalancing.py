"""Kind ``study_rebalancing`` end to end on synthetic Ken French and ECB files."""

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
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds.study_rebalancing import INPUTS

SDMX_HEADER = "KEY,FREQ,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT,UNIT_MULT"


def _zip(text: str, name: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


def _write_files(
    folder: Path, rng: np.random.Generator, *, gap: bool = False, kf_gap: bool = False
) -> dict[str, Path]:
    months = pd.date_range("2010-01-31", "2016-12-31", freq="ME")
    days = pd.bdate_range("2010-01-01", "2016-12-31")
    folder.mkdir(parents=True, exist_ok=True)
    mkt = 0.6 + 4.0 * rng.standard_normal(len(months))
    kf_lines = ["Synthetic developed factors.", "", ",Mkt-RF,SMB,HML,RF"]
    kf_lines += [
        f"{m.strftime('%Y%m')},{x:8.2f},{0.1:8.2f},{0.1:8.2f},{0.05:8.2f}"
        for m, x in zip(months, mkt, strict=True)
        if not (kf_gap and m == pd.Timestamp("2014-06-30"))
    ]
    kf_lines += ["", "Copyright test", ""]
    paths = {"kf_developed": folder / "Developed_3_Factors_CSV.zip"}
    paths["kf_developed"].write_bytes(_zip("\r\n".join(kf_lines), "Developed_3_Factors.csv"))

    usd = 1.2 * np.exp(np.cumsum(0.004 * rng.standard_normal(len(days))))
    march = (days >= pd.Timestamp("2013-03-01")) & (days <= pd.Timestamp("2013-03-31"))
    fx_days = days[~march] if gap else days
    usd_series = pd.Series(usd, index=days).loc[fx_days]
    newest_first = usd_series.iloc[::-1]
    fx_lines = ["Date,USD,JPY,"] + [
        f"{d.date().isoformat()},{v:.4f},130.00,"
        for d, v in zip(pd.DatetimeIndex(newest_first.index), newest_first.to_numpy(), strict=True)
    ]
    paths["ecb_fx"] = folder / "eurofxref-hist.zip"
    paths["ecb_fx"].write_bytes(_zip("\n".join(fx_lines) + "\n", "eurofxref-hist.csv"))

    level = 2.0 + np.cumsum(0.02 * rng.standard_normal(len(days)))
    for name, key, shift in (
        ("yc_6y", "SR_6Y", -0.1),
        ("yc_7y", "SR_7Y", 0.0),
    ):
        rows = [SDMX_HEADER] + [
            f"YC.B.U2.EUR.4F.G_N_A.SV_C_YM.{key},B,{d.date().isoformat()},{v + shift:.6f},A,PCPA,0"
            for d, v in zip(days, level, strict=True)
        ]
        paths[name] = folder / f"{name}.csv"
        paths[name].write_text("\n".join(rows) + "\n", encoding="utf-8")
    return paths


PARAMETERS = """
[parameters]
equity_weight = 0.6
policies = [
  "buy_and_hold", "calendar_monthly", "calendar_quarterly", "calendar_annual", "band_5_target",
  "band_10_target", "band_5_edge",
]
reference = "calendar_annual"
tax_rate = 0.26
initial_value = 100000
end = 2016-12-31
horizon_months = 48
n_paths = 3
mean_block_length = 6.0
support_share = 0.6667

[parameters.cost_scenarios]
low = { proportional = 0.0005, fixed = 2.0 }
high = { proportional = 0.002, fixed = 10.0 }
"""


def _config(tmp: Path, paths: dict[str, Path], *, out: str = "run", **replace: str) -> Path:
    inputs = "\n".join(f'{k} = "{v.as_posix()}"' for k, v in paths.items())
    body = PARAMETERS
    for old, new in replace.items():
        assert old in body, old
        body = body.replace(old, new)
    text = (
        '[experiment]\nname = "rebal"\nkind = "study_rebalancing"\n'
        'hypothesis = "Bands trade less than calendars for the same drift"\nseed = 5\n\n'
        f"[inputs]\n{inputs}\n{body}\n"
        f'[output]\ndirectory = "{(tmp / "results" / out).as_posix()}"\n'
    )
    path = tmp / f"rebal-{out}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _record(folder: Path) -> dict[str, object]:
    return json.loads((folder / "record.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_kind_inputs() -> None:
    kind = KINDS["study_rebalancing"]
    assert kind.inputs == tuple(INPUTS)
    assert kind.needs_seed


def test_study_runs_end_to_end_through_the_cli(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "data", rng)
    assert main(["run", str(_config(tmp_path, paths))]) == 0
    out = tmp_path / "results" / "run"
    record = _record(out)
    assert record["status"] == "success", record["error"]
    for name in (
        "asset_returns.csv",
        "historical.csv",
        "simulated_summary.csv",
        "simulated_runs.csv",
        "against_reference.csv",
        "hypotheses.csv",
    ):
        assert record["outputs"][name]["tag"] == "descriptive"  # type: ignore[index]
    returns = pd.read_csv(out / "asset_returns.csv", index_col=0)
    # January 2010 has no previous month end: 83 months of returns.
    assert len(returns) == 83
    assert list(returns.columns) == ["equity", "bond"]
    history = pd.read_csv(out / "historical.csv")
    assert len(history) == 2 * 7
    runs = pd.read_csv(out / "simulated_runs.csv")
    assert len(runs) == 3 * 2 * 7
    verdicts = pd.read_csv(out / "hypotheses.csv")
    assert len(verdicts) == 2 * 7  # per scenario: H1 2 conditions, H2 1, H3 4
    scalars = record["scalars"]
    assert scalars["months"]["value"] == 83.0  # type: ignore[index]
    assert "H2_low_supported" in scalars  # type: ignore[operator]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Paired differences against the reference policy" in html
    assert "not investment or tax advice" in html


def test_a_month_without_an_fx_rate_fails(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "gap", rng, gap=True)
    result = run_experiment(_config(tmp_path, paths, out="gap"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "no observation in month 2013-03-31" in str(result.record["error"])


def test_a_missing_equity_month_fails(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "kfgap", rng, kf_gap=True)
    result = run_experiment(_config(tmp_path, paths, out="kfgap"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "consecutive months" in str(result.record["error"])


def test_report_needs_results() -> None:
    from qrlab.studies.rebalancing_report import build_rebalancing_report

    with pytest.raises(ValidationError, match="historical and simulated"):
        build_rebalancing_report(
            title="T",
            hypothesis="H",
            facts=(),
            historical=pd.DataFrame(),
            simulated=pd.DataFrame(),
            comparison=pd.DataFrame(),
            verdicts=pd.DataFrame(),
        )


def test_sample_end_before_data_fails(tmp_path: Path, rng: np.random.Generator) -> None:
    paths = _write_files(tmp_path / "data", rng)
    early = _config(tmp_path, paths, out="early", **{"end = 2016-12-31": "end = 2005-12-31"})
    result = run_experiment(early, kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "no month has both equity and bond returns" in str(result.record["error"])


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("equity_weight = 0.6", "equity_weight = 1.0", "equity_weight"),
        ('"buy_and_hold", "calendar_monthly"', '"never", "calendar_monthly"', "unknown policies"),
        ('reference = "calendar_annual"', 'reference = "band_20"', "reference must be"),
        ("tax_rate = 0.26", "tax_rate = 1.0", "tax_rate"),
        ("initial_value = 100000", "initial_value = 0", "initial_value"),
        ("support_share = 0.6667", "support_share = 0.5", "support_share"),
        (
            "low = { proportional = 0.0005, fixed = 2.0 }\n"
            "high = { proportional = 0.002, fixed = 10.0 }",
            "",
            "cost_scenarios",
        ),
    ],
)
def test_parameters_are_validated(tmp_path: Path, old: str, new: str, message: str) -> None:
    paths = {k: tmp_path / f"{k}.bin" for k in INPUTS}
    for path in paths.values():
        path.write_bytes(b"x")
    with pytest.raises(ValidationError, match=message):
        validate_experiment(_config(tmp_path, paths, **{old: new}), kinds=KINDS)
