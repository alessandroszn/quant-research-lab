"""The working paper's numbers and tables come from the study records (design note 6.3d)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import paper_values
import pytest

ROOT = Path(__file__).parents[3]


def _results(tmp: Path) -> Path:
    run = tmp / "results" / "studies" / "study-x" / "main"
    run.mkdir(parents=True)
    record = {
        "seed": 7,
        "code": {"git_commit": "abc123"},  # truncated to 3
        "configurations_tried": 3,
        "inputs": {
            "prices": {"given": r"..\data\raw\p.csv", "bytes": 1234, "sha256": "ab" * 32},
            "ff3": {"given": "../data/raw/ff3.zip", "bytes": 9, "sha256": "cd" * 32},
        },
        "scalars": {"dsr": {"value": 0.8765, "tag": "descriptive"}},
    }
    (run / "record.json").write_text(json.dumps(record), encoding="utf-8")
    pd.DataFrame(
        {
            "strategy": ["ew", "vw", "minvar"],
            "window": [60, 60, 120],
            "sharpe": [0.4833, -0.0004, 1234.5678],
            "note": ["a", "b", float("nan")],
        }
    ).to_csv(run / "performance.csv")
    return tmp / "results" / "studies"


def _paper(tmp: Path, spec: str) -> Path:
    paper = tmp / "docs" / "paper"
    (paper / "values").mkdir(parents=True)
    (paper / "values" / "x.toml").write_text(spec, encoding="utf-8")
    return paper


SPEC = """
[values.ew_sharpe]
run = "study-x/main"
table = "performance.csv"
where = { strategy = "ew", window = 60 }
column = "sharpe"
decimals = 2

[values.vw_sharpe_pct]
run = "study-x/main"
table = "performance.csv"
where = { strategy = "vw" }
column = "sharpe"
decimals = 1
scale = 100
unit = " %"

[values.big_abs]
run = "study-x/main"
table = "performance.csv"
where = { strategy = "minvar" }
column = "sharpe"
decimals = 0
scale = -1
absolute = true

[values.dsr]
run = "study-x/main"
scalar = "dsr"
decimals = 3

[values.tiny_p]
run = "study-x/main"
table = "performance.csv"
where = { strategy = "vw" }
column = "sharpe"
decimals = 3
absolute = true
below = 0.001

[values.tried]
run = "study-x/main"
record = "configurations_tried"

[values.commit]
run = "study-x/main"
record = "code.git_commit"
truncate = 3

[values.label]
run = "study-x/main"
table = "performance.csv"
where = { strategy = "ew" }
column = "strategy"

[tables.sharpes]
run = "study-x/main"
table = "performance.csv"
where = { window = 60 }
columns = [
    { column = "strategy", header = "Strategy" },
    { column = "sharpe", header = "Sharpe", decimals = 2 },
]

[tables.inputs]
inputs_of = "study-x/main"

[tables.notes]
run = "study-x/main"
table = "performance.csv"
columns = [{ column = "note", header = "Note", decimals = 0 }]
"""


def test_format_number_by_hand() -> None:
    fmt = paper_values.format_number
    assert fmt(0.4833, decimals=2, scale=1, unit="", absolute=False) == "0.48"
    assert fmt(0.8765, decimals=3, scale=1, unit="", absolute=False) == "0.877"  # half-up
    assert fmt(-0.584, decimals=0, scale=100, unit=" %", absolute=False) == "-58 %"
    assert fmt(-0.584, decimals=0, scale=100, unit=" %", absolute=True) == "58 %"
    assert fmt(1234567.8, decimals=0, scale=1, unit="", absolute=False) == "1,234,568"
    assert fmt(-0.0004, decimals=2, scale=1, unit="", absolute=False) == "0.00"  # no "-0.00"
    with pytest.raises(ValueError, match="non-finite"):
        fmt(math.nan, decimals=2, scale=1, unit="", absolute=False)


def test_generate_values_and_tables(tmp_path: Path) -> None:
    files = paper_values.generate(_results(tmp_path), _paper(tmp_path, SPEC))
    values = json.loads(files["_generated/values.json"])
    assert values == {
        "big_abs": "1,235",
        "commit": "abc",
        "dsr": "0.877",
        "ew_sharpe": "0.48",
        "label": "ew",
        "tiny_p": "< 0.001",  # |-0.0004| is below the floor of 0.001
        "tried": "3",
        "vw_sharpe_pct": "0.0 %",  # a rounded zero has no sign
    }
    assert files["_generated/sharpes.md"] == (
        "| Strategy | Sharpe |\n|---|---:|\n| ew | 0.48 |\n| vw | 0.00 |\n"
    )
    assert files["_generated/notes.md"].splitlines()[-1] == "| — |"
    assert files["_generated/inputs.md"].splitlines()[2:] == [
        "| ff3 | ff3.zip | 9 | cdcdcdcdcdcdcdcd |",
        "| prices | p.csv | 1,234 | abababababababab |",  # Windows paths too
    ]


def test_check_mode(tmp_path: Path) -> None:
    results, paper = _results(tmp_path), _paper(tmp_path, SPEC)
    assert paper_values.write_or_check(results, paper, check=True) != []  # nothing written yet
    assert paper_values.write_or_check(results, paper, check=False) == []
    assert paper_values.write_or_check(results, paper, check=True) == []
    table = results / "study-x" / "main" / "performance.csv"
    table.write_text(table.read_text(encoding="utf-8").replace("0.4833", "0.4999"), "utf-8")
    assert paper_values.write_or_check(results, paper, check=True) == [
        "_generated/sharpes.md",  # 0.48 becomes 0.50 in the table too
        "_generated/values.json",
    ]


A = '[values.a]\nrun = "study-x/main"\n'


@pytest.mark.parametrize(
    ("spec", "error", "message"),
    [
        ('[values.a]\nrun = "nope"\nscalar = "dsr"\n', FileNotFoundError, "no record"),
        (
            '[values.a]\nrun = "study-x/main"\ntable = "nope.csv"\ncolumn = "x"\n',
            FileNotFoundError,
            "no table",
        ),
        (
            A + 'table = "performance.csv"\nwhere = { window = 60 }\ncolumn = "sharpe"\n',
            ValueError,
            "2 rows",
        ),
        (
            A + 'table = "performance.csv"\nwhere = { nope = 1 }\ncolumn = "sharpe"\n',
            KeyError,
            "no column",
        ),
        (
            '[tables.t]\nrun = "study-x/main"\n'
            'table = "performance.csv"\nwhere = { window = 1 }\ncolumns = []\n',
            ValueError,
            "no rows",
        ),
        (
            '[values.dsr]\nrun = "study-x/main"\nscalar = "dsr"\n'
            '[values.ew_sharpe]\nrun = "study-x/main"\nscalar = "dsr"\n',
            ValueError,
            "twice",
        ),
    ],
)
def test_errors(tmp_path: Path, spec: str, error: type[Exception], message: str) -> None:
    results, paper = _results(tmp_path), _paper(tmp_path, SPEC if "twice" in message else spec)
    if "twice" in message:
        (paper / "values" / "y.toml").write_text(spec, encoding="utf-8")
    with pytest.raises(error, match=message):
        paper_values.generate(results, paper)


def test_substitutions_used(tmp_path: Path) -> None:
    paper = _paper(tmp_path, SPEC)
    (paper / "a.md").write_text("Sharpe {{ ew_sharpe }} and {{dsr}}.", encoding="utf-8")
    (paper / "_generated").mkdir()
    (paper / "_generated" / "t.md").write_text("{{ ignored }}", encoding="utf-8")
    assert paper_values.substitutions_used(paper) == {"ew_sharpe", "dsr"}


def test_command_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _results(tmp_path)
    _paper(tmp_path, SPEC)
    assert paper_values.main(["--check"], root=tmp_path) == 1
    assert "differs from the records" in capsys.readouterr().out
    assert paper_values.main([], root=tmp_path) == 0
    assert paper_values.main(["--check"], root=tmp_path) == 0
    assert paper_values.main(["--nope"], root=tmp_path) == 2


def test_the_paper_uses_every_value_and_defines_every_substitution() -> None:
    """The committed paper: no stale value, no undefined substitution."""
    paper = ROOT / "docs" / "paper"
    values_file = paper / "_generated" / "values.json"
    if not values_file.is_file():  # pragma: no cover - before the paper exists
        pytest.skip("the paper has not been generated yet")
    values = set(json.loads(values_file.read_text(encoding="utf-8")))
    used = paper_values.substitutions_used(paper)
    assert used - values == set(), "used in the paper but not generated"
    assert values - used == set(), "generated but not used in the paper"
