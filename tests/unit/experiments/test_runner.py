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
    staging_dir,
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


# -------------------------------------------------------------- frozen builds (design 6.2)
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _frozen(monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    """Pretend to be a PyInstaller program in ``folder``; starting a process fails the test."""
    import subprocess
    import sys

    def no_process(*args: object, **kwargs: object) -> None:
        raise AssertionError("a frozen build must not start git")

    monkeypatch.setattr(subprocess, "run", no_process)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(folder / "qrlab.exe"))


def test_frozen_record_takes_the_commit_from_build_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = tmp_path / "program"
    program.mkdir()
    info = {"commit": COMMIT, "dirty": False, "built": "2026-11-13T10:00:00+00:00"}
    (program / "build-info.json").write_text(json.dumps(info), encoding="utf-8")
    _frozen(monkeypatch, program)
    result = run_experiment(_write(tmp_path), kinds=KINDS, overwrite=False)
    code = result.record["code"]
    assert code["frozen"] is True
    assert code["git_commit"] == COMMIT
    assert code["git_dirty"] is False
    assert code["built"] == "2026-11-13T10:00:00+00:00"
    assert set(code["packages"]) == {"numpy", "pandas", "scipy", "statsmodels", "matplotlib"}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "no build-info.json"),
        ("{not json", "not valid JSON"),
        ('{"commit": "abc", "dirty": false, "built": "x"}', "commit"),
        (json.dumps({"commit": COMMIT, "dirty": True, "built": "x"}), "dirty"),
        (json.dumps({"commit": COMMIT, "dirty": False}), "built"),
        ("[1, 2]", "JSON object"),
    ],
)
def test_frozen_build_info_must_be_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str | None, message: str
) -> None:
    program = tmp_path / "program"
    program.mkdir()
    if content is not None:
        (program / "build-info.json").write_text(content, encoding="utf-8")
    _frozen(monkeypatch, program)
    config = _write(tmp_path)
    with pytest.raises(ValidationError, match=message):
        run_experiment(config, kinds=KINDS, overwrite=False)
    assert not (tmp_path / "results" / "demo").exists()  # refused before writing anything


def test_source_runs_are_marked_not_frozen(tmp_path: Path) -> None:
    result = run_experiment(_write(tmp_path), kinds=KINDS, overwrite=False)
    assert result.record["code"]["frozen"] is False
    assert "built" not in result.record["code"]


def test_records_carry_their_format(tmp_path: Path) -> None:
    from qrlab.experiments import RECORD_FORMAT

    assert RECORD_FORMAT == 1
    result = run_experiment(_write(tmp_path), kinds=KINDS, overwrite=False)
    assert result.record["format"] == 1
    written = json.loads((result.output_dir / "record.json").read_text(encoding="utf-8"))
    assert written["format"] == 1


# ------------------------------------------------------------------- notices (design 7.2)
def _run_with_notice(context: RunContext) -> ExperimentOutput:
    plain = _run(context)
    return ExperimentOutput(tables=plain.tables, scalars=plain.scalars, notice="Read me first.")


NOTED = {
    "scale": ExperimentKind(
        "scale", "Scale with a notice", ("data",), False, ("scale",), _parse, _run_with_notice
    )
}


def test_a_notice_is_written_and_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run_experiment(_write(tmp_path), kinds=NOTED, overwrite=False)
    assert result.succeeded
    notice = result.output_dir / "NOTICE.txt"
    assert notice.read_text(encoding="utf-8") == "Read me first.\n"
    assert result.record["outputs"]["NOTICE.txt"]["tag"] == "descriptive"
    assert result.record["notice"] == "Read me first."
    assert main(["run", str(_write(tmp_path)), "--overwrite"], kinds=NOTED) == 0
    assert "notice: Read me first." in capsys.readouterr().out


def test_no_notice_no_file(tmp_path: Path) -> None:
    result = run_experiment(_write(tmp_path), kinds=KINDS, overwrite=False)
    assert result.record["notice"] is None
    assert not (result.output_dir / "NOTICE.txt").exists()


def test_a_notice_must_be_text(tmp_path: Path) -> None:
    def bad(context: RunContext) -> ExperimentOutput:
        return ExperimentOutput(notice="  ")

    kinds = {
        "scale": ExperimentKind("scale", "Bad notice", ("data",), False, ("scale",), _parse, bad)
    }
    result = run_experiment(_write(tmp_path), kinds=kinds, overwrite=False)
    assert not result.succeeded
    assert "notice" in result.record["error"]
    assert result.record["notice"] is None


# --------------------------------------------------------------- interruption-safe outputs (12.2)
def _interrupting(error: type[BaseException]) -> dict[str, ExperimentKind]:
    def run(context: RunContext) -> ExperimentOutput:
        raise error()

    return {"scale": ExperimentKind("scale", "", ("data",), False, ("scale",), _parse, run)}


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


def _ledger_lines(folder: Path) -> int:
    return len((folder / "trials.jsonl").read_text(encoding="utf-8").splitlines())


@pytest.mark.parametrize("error", [KeyboardInterrupt, SystemExit])
def test_an_interrupted_run_keeps_the_earlier_outputs(
    tmp_path: Path, error: type[BaseException]
) -> None:
    config = _write(tmp_path)
    first = run_experiment(config, kinds=KINDS, overwrite=False)
    before = _snapshot(first.output_dir)
    with pytest.raises(error):
        run_experiment(config, kinds=_interrupting(error), overwrite=True)
    assert _snapshot(first.output_dir) == before
    assert not staging_dir(first.output_dir).exists()
    assert sorted(p.name for p in first.output_dir.parent.iterdir()) == ["demo", "trials.jsonl"]
    assert _ledger_lines(first.output_dir.parent) == 1  # an interrupted run is not a trial


def test_an_interrupted_first_run_leaves_nothing(tmp_path: Path) -> None:
    config = _write(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        run_experiment(config, kinds=_interrupting(KeyboardInterrupt), overwrite=False)
    assert list((tmp_path / "results").iterdir()) == []
    assert count_trials(tmp_path / "results", "demo") == 0


def test_a_staging_folder_left_by_an_ended_process_is_replaced(tmp_path: Path) -> None:
    config = _write(tmp_path)
    out = tmp_path / "results" / "demo"
    staging = staging_dir(out)
    assert staging == tmp_path / "results" / ".demo.partial"
    staging.mkdir(parents=True)
    (staging / "record.json").write_text("{}", encoding="utf-8")
    (staging / "stale.csv").write_text("x\n", encoding="utf-8")
    old = tmp_path / "results" / ".demo.old"
    old.mkdir()
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded
    assert not staging.exists()
    assert not old.exists()
    assert not (out / "stale.csv").exists()
    assert json.loads((out / "record.json").read_text(encoding="utf-8"))["status"] == "success"


def test_a_failed_run_replaces_the_earlier_outputs_and_is_a_trial(tmp_path: Path) -> None:
    run_experiment(_write(tmp_path), kinds=KINDS, overwrite=False)
    failed = run_experiment(_write(tmp_path, extra="fail = true"), kinds=KINDS, overwrite=True)
    assert not failed.succeeded
    assert sorted(p.name for p in failed.output_dir.iterdir()) == ["record.json"]
    assert _ledger_lines(failed.output_dir.parent) == 2
    assert failed.record["configurations_tried"] == 2  # two configs: with and without fail


@pytest.mark.parametrize("earlier", [True, False])
def test_outputs_that_cannot_be_moved_into_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, earlier: bool
) -> None:
    config = _write(tmp_path)
    out = tmp_path / "results" / "demo"
    if earlier:
        run_experiment(config, kinds=KINDS, overwrite=False)
        before = _snapshot(out)
    rename = Path.rename

    def locked(self: Path, target: Path) -> Path:
        if self.name == ".demo.partial":
            raise OSError("a file is open")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", locked)
    with pytest.raises(ValidationError, match=r"cannot replace .*demo: a file is open; this run"):
        run_experiment(config, kinds=KINDS, overwrite=True)
    staging = staging_dir(out)
    assert (staging / "record.json").exists()  # this run's outputs are kept, and named
    if earlier:
        assert _snapshot(out) == before  # the earlier outputs are back in place
        assert _ledger_lines(out.parent) == 1
    else:
        assert not out.exists()
        assert not (out.parent / "trials.jsonl").exists()


def test_the_cli_reports_a_cancelled_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _write(tmp_path)
    assert main(["run", str(config)], kinds=_interrupting(KeyboardInterrupt)) == 130
    assert capsys.readouterr().err == "cancelled: the earlier outputs are unchanged\n"
