"""The experiment runner and the CLI, with a test kind (design note 5.2)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import pandas as pd
import pytest

from qrlab.cli import main
from qrlab.core.errors import ValidationError
from qrlab.experiments import (
    ExperimentKind,
    ExperimentOutput,
    RunContext,
    Tagged,
    count_trials,
    file_sha256,
    load_config,
    require_keys,
    run_experiment,
    validate_experiment,
)


def _parse(parameters: Mapping[str, object]) -> float:
    require_keys(parameters, required={"scale"}, optional={"fail"}, where="[parameters]")
    scale = parameters["scale"]
    if type(scale) is not float:
        raise ValidationError("scale must be a float")
    if parameters.get("fail"):
        return -scale
    return scale


def _run(context: RunContext) -> ExperimentOutput:
    scale = cast(float, context.parameters)
    if scale < 0:
        raise RuntimeError("the test kind was asked to fail")
    values = pd.read_csv(context.inputs["data"])["x"] * scale
    return ExperimentOutput(
        tables={"scaled": Tagged(values.to_frame(), "descriptive")},
        scalars={
            "total": Tagged(float(values.sum()), "in_sample"),
            "note": Tagged("ok", "descriptive"),
        },
        figures={"tiny": b"\x89PNG\r\n\x1a\nfake"},
        report_html="<p>report</p>",
    )


SCALE = ExperimentKind("scale", "Multiply a column", ("data",), False, ("scale",), _parse, _run)
KINDS = {"scale": SCALE}


def _write(
    tmp: Path, *, scale: str = "2.0", extra: str = "", name: str = "demo", out: str = "results/demo"
) -> Path:
    (tmp / "data.csv").write_text("x\n1\n2\n3\n", encoding="utf-8")
    config = tmp / "experiment.toml"
    config.write_text(
        f'[experiment]\nname = "{name}"\nkind = "scale"\nhypothesis = "descriptive"\n\n'
        f'[inputs]\ndata = "data.csv"\n\n[parameters]\nscale = {scale}\n{extra}\n'
        f'[output]\ndirectory = "{out}"\n',
        encoding="utf-8",
    )
    return config


def test_run_writes_outputs_and_record(tmp_path: Path) -> None:
    result = run_experiment(_write(tmp_path), kinds=KINDS, overwrite=False)
    assert result.succeeded
    out = result.output_dir
    assert sorted(p.name for p in out.iterdir()) == [
        "record.json",
        "report.html",
        "scaled.csv",
        "tiny.png",
    ]
    record = json.loads((out / "record.json").read_text(encoding="utf-8"))
    assert record["experiment"] == {"name": "demo", "kind": "scale", "hypothesis": "descriptive"}
    assert record["inputs"]["data"]["given"] == "data.csv"
    assert record["inputs"]["data"]["sha256"] == file_sha256(tmp_path / "data.csv")
    assert record["outputs"]["scaled.csv"]["tag"] == "descriptive"
    assert record["scalars"]["total"] == {"value": 12.0, "tag": "in_sample"}
    assert record["configurations_tried"] == 1
    assert record["status"] == "success"
    assert record["code"]["qrlab"]
    assert set(record["code"]["packages"]) == {
        "numpy",
        "pandas",
        "scipy",
        "statsmodels",
        "matplotlib",
    }


def test_known_hash_and_reproducible_outputs(tmp_path: Path) -> None:
    (tmp_path / "abc.txt").write_bytes(b"abc")
    assert (
        file_sha256(tmp_path / "abc.txt")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    config = _write(tmp_path)
    first = run_experiment(config, kinds=KINDS, overwrite=False)
    csv_first = (first.output_dir / "scaled.csv").read_bytes()
    second = run_experiment(config, kinds=KINDS, overwrite=True)
    assert (second.output_dir / "scaled.csv").read_bytes() == csv_first
    assert first.record["outputs"] == second.record["outputs"]
    assert second.record["configurations_tried"] == 1


def test_trial_counting(tmp_path: Path) -> None:
    run_experiment(_write(tmp_path), kinds=KINDS, overwrite=False)
    run_experiment(_write(tmp_path), kinds=KINDS, overwrite=True)
    changed = run_experiment(_write(tmp_path, scale="3.0"), kinds=KINDS, overwrite=True)
    assert changed.record["configurations_tried"] == 2
    ledger = (tmp_path / "results" / "trials.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 3
    moved = run_experiment(
        _write(tmp_path, scale="3.0", out="results/elsewhere"), kinds=KINDS, overwrite=False
    )
    assert moved.record["configurations_tried"] == 2  # [output] is not part of the config hash
    assert count_trials(tmp_path / "results", "demo") == 2
    assert count_trials(tmp_path / "results", "other") == 0
    assert count_trials(tmp_path / "nowhere", "demo") == 0


def test_existing_output_needs_overwrite(tmp_path: Path) -> None:
    config = _write(tmp_path)
    run_experiment(config, kinds=KINDS, overwrite=False)
    with pytest.raises(ValidationError, match="overwrite"):
        run_experiment(config, kinds=KINDS, overwrite=False)


def test_failures_are_recorded(tmp_path: Path) -> None:
    result = run_experiment(_write(tmp_path, extra="fail = true"), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "the test kind was asked to fail" in str(result.record["error"])
    assert (result.output_dir / "record.json").exists()
    assert result.record["outputs"] == {}


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (lambda t: t.replace('kind = "scale"', 'kind = "nope"'), "unknown experiment kind"),
        (lambda t: t.replace("scale = 2.0", "scale = 2.0\ntypo = 1"), "unknown keys"),
        (lambda t: t.replace("scale = 2.0", ""), "missing"),
        (lambda t: t.replace('data = "data.csv"', 'data = "absent.csv"'), "does not exist"),
        (
            lambda t: t.replace('data = "data.csv"', 'data = "data.csv"\nmore = "data.csv"'),
            "unknown",
        ),
        (
            lambda t: t.replace(
                'hypothesis = "descriptive"', 'hypothesis = "descriptive"\nseed = 1'
            ),
            "no random",
        ),
        (lambda t: t.replace('hypothesis = "descriptive"', 'hypothesis = ""'), "non-empty"),
        (lambda t: t.replace('hypothesis = "descriptive"', 'hypothesis = "x"\nseed = -1'), "seed"),
        (lambda t: t.replace("[output]", "[outputs]"), "missing"),
        (lambda t: t.replace('directory = "results/demo"', 'directory = ""'), "directory"),
        (lambda t: t.replace('data = "data.csv"', "data = 3"), "file path"),
        (lambda t: t + "\n[extra]\n", "unknown"),
        (lambda t: "not = valid = toml", "invalid TOML"),
    ],
)
def test_config_errors(tmp_path: Path, change: Callable[[str], str], match: str) -> None:
    config = _write(tmp_path)
    config.write_text(change(config.read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(ValidationError, match=match):
        validate_experiment(config, kinds=KINDS)


def test_tables_must_be_tables_and_seed_rules(tmp_path: Path) -> None:
    config = _write(tmp_path)
    text = config.read_text(encoding="utf-8").replace("[parameters]\nscale = 2.0\n", "")
    config.write_text("parameters = 1\n" + text, encoding="utf-8")
    with pytest.raises(ValidationError, match="must be a table"):
        load_config(config)
    seeded = ExperimentKind("seeded", "needs a seed", ("data",), True, ("scale",), _parse, _run)
    config = _write(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8").replace('kind = "scale"', 'kind = "seeded"'),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="seed is required"):
        validate_experiment(config, kinds={"seeded": seeded})
    with pytest.raises(ValidationError, match="does not exist"):
        load_config(tmp_path / "missing.toml")


def test_kind_output_rules(tmp_path: Path) -> None:
    def bad_table(context: RunContext) -> ExperimentOutput:
        return ExperimentOutput(tables={"x": Tagged(1.0, "descriptive")})

    def bad_scalar(context: RunContext) -> ExperimentOutput:
        return ExperimentOutput(scalars={"x": Tagged(pd.DataFrame(), "descriptive")})

    for run in (bad_table, bad_scalar):
        kind = ExperimentKind("scale", "", ("data",), False, ("scale",), _parse, run)
        result = run_experiment(_write(tmp_path), kinds={"scale": kind}, overwrite=True)
        assert not result.succeeded
    with pytest.raises(ValidationError, match="tag"):
        Tagged(1.0, "maybe")


def test_input_changed_during_the_run(tmp_path: Path) -> None:
    def tamper(context: RunContext) -> ExperimentOutput:
        context.inputs["data"].write_text("x\n9\n", encoding="utf-8")
        return ExperimentOutput()

    kind = ExperimentKind("scale", "", ("data",), False, ("scale",), _parse, tamper)
    result = run_experiment(_write(tmp_path), kinds={"scale": kind}, overwrite=False)
    assert "changed during the run" in str(result.record["error"])


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _write(tmp_path)
    assert main(["kinds"], kinds=KINDS) == 0
    assert "scale: Multiply a column" in capsys.readouterr().out
    assert main(["validate", str(config)], kinds=KINDS) == 0
    assert "valid: demo (scale)" in capsys.readouterr().out
    assert main(["run", str(config)], kinds=KINDS) == 0
    assert "configurations tried: 1" in capsys.readouterr().out
    assert main(["run", str(config)], kinds=KINDS) == 2  # exists, no --overwrite
    assert "overwrite" in capsys.readouterr().err
    assert main(["run", str(config), "--overwrite"], kinds=KINDS) == 0
    failing = _write(tmp_path, extra="fail = true")
    assert main(["run", str(failing), "--overwrite"], kinds=KINDS) == 1
    assert "asked to fail" in capsys.readouterr().err
    assert main(["validate", str(tmp_path / "missing.toml")], kinds=KINDS) == 2


def test_record_without_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def no_git(*args: object, **kwargs: object) -> None:
        raise OSError("git is not installed")

    monkeypatch.setattr(subprocess, "run", no_git)
    result = run_experiment(_write(tmp_path), kinds=KINDS, overwrite=False)
    assert result.record["code"]["git_commit"] is None
    assert result.record["code"]["git_dirty"] is None
