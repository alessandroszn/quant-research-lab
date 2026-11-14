"""Groups of input files in a config (design 7.4a): flattened, checked, hashed and recorded."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import pytest

from qrlab.cli import main
from qrlab.core.errors import ValidationError
from qrlab.experiments import (
    ExperimentKind,
    ExperimentOutput,
    RunContext,
    Tagged,
    file_sha256,
    load_config,
    run_experiment,
    validate_experiment,
)
from qrlab.experiments.workspace import config_template


def _parse(parameters: Mapping[str, object]) -> None:
    return None


def _run(context: RunContext) -> ExperimentOutput:
    parts = context.group("parts")
    total = sum(float(pd.read_csv(path)["x"].sum()) for path in parts.values())
    return ExperimentOutput(
        tables={"keys": Tagged(pd.DataFrame({"key": sorted(parts)}), "descriptive")},
        scalars={"total": Tagged(total, "descriptive")},
    )


GROUPED = ExperimentKind(
    "grouped",
    "Sum a column over a group of files",
    ("main",),
    False,
    (),
    _parse,
    _run,
    optional_inputs=("extra",),
    input_groups=("parts",),
)
KINDS = {"grouped": GROUPED}


def _write(tmp: Path, inputs: str) -> Path:
    for name, rows in {"main": "1", "a": "1\n2", "b": "10", "extra": "0"}.items():
        (tmp / f"{name}.csv").write_text(f"x\n{rows}\n", encoding="utf-8")
    config = tmp / "experiment.toml"
    config.write_text(
        '[experiment]\nname = "g"\nkind = "grouped"\nhypothesis = "descriptive"\n\n'
        f"{inputs}\n[parameters]\n\n"
        '[output]\ndirectory = "out"\n',
        encoding="utf-8",
    )
    return config


GOOD = '[inputs]\nmain = "main.csv"\n\n[inputs.parts]\nIE0000000012 = "a.csv"\nusd = "b.csv"\n'


def test_a_group_is_flattened(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, GOOD))
    assert sorted(config.inputs) == ["main", "parts.IE0000000012", "parts.usd"]
    assert config.inputs["parts.usd"] == (tmp_path / "b.csv").resolve()
    assert config.given_inputs["parts.usd"] == "b.csv"
    assert config.input_groups == frozenset({"parts"})


def test_a_group_is_hashed_recorded_and_given_to_the_kind(tmp_path: Path) -> None:
    result = run_experiment(_write(tmp_path, GOOD), kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    record = json.loads((result.output_dir / "record.json").read_text(encoding="utf-8"))
    assert sorted(record["inputs"]) == ["main", "parts.IE0000000012", "parts.usd"]
    assert record["inputs"]["parts.usd"]["sha256"] == file_sha256(tmp_path / "b.csv")
    assert record["inputs"]["parts.usd"]["given"] == "b.csv"
    assert record["scalars"]["total"]["value"] == 13.0
    keys = pd.read_csv(result.output_dir / "keys.csv")["key"].tolist()
    assert keys == ["IE0000000012", "usd"]


def test_a_group_may_be_absent(tmp_path: Path) -> None:
    result = run_experiment(
        _write(tmp_path, '[inputs]\nmain = "main.csv"\n'), kinds=KINDS, overwrite=False
    )
    assert result.succeeded
    assert result.record["scalars"]["total"]["value"] == 0.0


@pytest.mark.parametrize(
    ("inputs", "match"),
    [
        ('[inputs]\nmain = "main.csv"\n\n[inputs.extra]\nk = "a.csv"\n', "extra is not a group"),
        ('[inputs]\nmain = "main.csv"\nparts = "a.csv"\n', "parts must be a table of files"),
        ('[inputs.main]\nk = "main.csv"\n', "main is not a group"),
        ('[inputs]\nmain = "main.csv"\nparts = {}\n', "parts has no files"),
        ('[inputs]\nmain = "main.csv"\nparts = { "a.b" = "a.csv" }\n', "key 'a.b'"),
        ('[inputs]\nmain = "main.csv"\nparts = { "" = "a.csv" }\n', "key ''"),
        ('[inputs]\nmain = "main.csv"\nparts = { k = 3 }\n', r"parts\.k must be a file path"),
        (
            '[inputs]\nmain = "main.csv"\nparts = { k = "missing.csv" }\n',
            r"parts\.k: .* does not exist",
        ),
        (
            '[inputs]\nmain = "main.csv"\nparts = { k = { j = "a.csv" } }\n',
            r"parts\.k must be a file path",
        ),
    ],
)
def test_group_errors(tmp_path: Path, inputs: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_write(tmp_path, inputs), kinds=KINDS)


def test_a_group_file_changed_during_the_run(tmp_path: Path) -> None:
    def changing(context: RunContext) -> ExperimentOutput:
        context.group("parts")["usd"].write_text("x\n99\n", encoding="utf-8")
        return ExperimentOutput()

    kinds = {
        "grouped": ExperimentKind(
            "grouped", "d", ("main",), False, (), _parse, changing, input_groups=("parts",)
        )
    }
    result = run_experiment(_write(tmp_path, GOOD), kinds=kinds, overwrite=False)
    assert not result.succeeded
    assert "changed during the run" in str(result.record["error"])


def test_groups_in_the_template_and_the_cli(capsys: pytest.CaptureFixture[str]) -> None:
    template = config_template(GROUPED)
    assert "# [inputs.parts]  # optional group: one file per key" in template
    assert '# KEY = "../data/FILL-IN"' in template
    assert main(["kinds"]) == 0
    printed = capsys.readouterr().out
    assert "  optional input groups: extra_prices, extra_prices_mapping" in printed


def test_group_of_an_unknown_name_in_the_context(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, GOOD))
    context = RunContext(config, None, dict(config.inputs), None)
    assert context.group("nothing") == {}
    assert sorted(context.group("parts")) == ["IE0000000012", "usd"]
