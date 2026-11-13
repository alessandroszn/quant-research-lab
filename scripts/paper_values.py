"""Generate every number and table of the working paper from the study records (design 6.3d).

Usage, from the repository root:

    uv run python scripts/paper_values.py            # write docs/paper/_generated/
    uv run python scripts/paper_values.py --check    # fail if the committed files differ

The values are declared in ``docs/paper/values/*.toml``, one file per part of the paper. No
number in the paper is typed by hand: the text uses MyST substitutions (``{{ name }}``) that
the docs build fills in from ``values.json``, and tables are included from generated files.

A value is a table such as::

    [values.s2_ew_sharpe]
    run = "one-over-n/paper"           # folder under the results root
    table = "performance.csv"          # or: scalar = "dsr_probability"; or: record = "seed"
    where = { dataset = "industries_10", window = 60, cost_per_unit = 0.0, strategy = "ew" }
    column = "sharpe"
    decimals = 2                       # numbers only
    scale = 1.0                        # optional, e.g. 100 for percentages
    unit = ""                          # optional, e.g. " %" or " bp"
    absolute = false                   # optional: report the magnitude
    truncate = 10                      # text only, optional: keep the first characters
    below = 0.0001                     # optional: print "< 0.0001" for smaller magnitudes

``where`` must select exactly one row. A table of the paper is::

    [tables.s2_sharpe]
    run = "one-over-n/paper"
    table = "performance.csv"
    where = { dataset = "industries_10", window = 60, cost_per_unit = 0.0 }
    columns = [
        { column = "strategy", header = "Strategy" },
        { column = "sharpe", header = "Sharpe", decimals = 2 },
    ]

A column may map recorded identifiers to readable labels:
``{ column = "strategy", header = "Strategy", labels = { ew = "1/N" } }``.
"""

from __future__ import annotations

import json
import math
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from qrlab.reporting import EN
from qrlab.reporting import format_number as reporting_number

__all__ = [
    "SUBSTITUTION",
    "format_number",
    "generate",
    "main",
    "resolve_value",
    "substitutions_used",
    "write_or_check",
]

SUBSTITUTION = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
GENERATED = "_generated"


def format_number(value: float, *, decimals: int, scale: float, unit: str, absolute: bool) -> str:
    """Format a number for the text: scaled, with its unit.

    Rounding is half-up on the decimal value with thousands separators, exactly as in the
    reports (:func:`qrlab.reporting.format_number`); a rounded zero has no sign.
    """
    if not math.isfinite(value):
        raise ValueError(f"cannot format a non-finite value ({value})")
    number = abs(value * scale) if absolute else value * scale
    return reporting_number(number, decimals, style=EN) + unit


def _record(results: Path, run: str) -> dict[str, Any]:
    path = results / run / "record.json"
    if not path.is_file():
        raise FileNotFoundError(f"no record for run {run!r} at {path}")
    record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return record


def _rows(results: Path, spec: Mapping[str, Any]) -> pd.DataFrame:
    path = results / spec["run"] / spec["table"]
    if not path.is_file():
        raise FileNotFoundError(f"no table {spec['table']!r} for run {spec['run']!r}")
    frame = pd.read_csv(path, index_col=0)
    frame = frame.reset_index(names="index") if frame.index.name is None else frame.reset_index()
    for column, wanted in spec.get("where", {}).items():
        if column not in frame.columns:
            raise KeyError(f"{spec['table']} has no column {column!r}")
        frame = frame[frame[column].astype(str) == str(wanted)]
    return frame


def resolve_value(results: Path, name: str, spec: Mapping[str, Any]) -> str:
    """Return the formatted text of one value."""
    if "record" in spec:
        node: Any = _record(results, spec["run"])
        for key in str(spec["record"]).split("."):
            node = node[key]
        raw: Any = node
    elif "scalar" in spec:
        raw = _record(results, spec["run"])["scalars"][spec["scalar"]]["value"]
    else:
        rows = _rows(results, spec)
        if len(rows) != 1:
            raise ValueError(f"{name}: 'where' selects {len(rows)} rows, not 1")
        raw = rows.iloc[0][spec["column"]]
    if isinstance(raw, str) or "decimals" not in spec:
        text = str(raw)
        return text[: int(spec["truncate"])] if "truncate" in spec else text
    number, decimals = float(raw), int(spec["decimals"])
    scale, unit = float(spec.get("scale", 1.0)), str(spec.get("unit", ""))
    if "below" in spec and abs(number * scale) < float(spec["below"]):
        floor = format_number(
            float(spec["below"]), decimals=decimals, scale=1.0, unit=unit, absolute=False
        )
        return f"< {floor}"
    return format_number(
        number,
        decimals=decimals,
        scale=scale,
        unit=unit,
        absolute=bool(spec.get("absolute", False)),
    )


def _cell(raw: Any, column: Mapping[str, Any]) -> str:
    labels: Mapping[str, str] = column.get("labels", {})
    if str(raw) in labels:
        return labels[str(raw)]
    if "decimals" not in column or isinstance(raw, str):
        return str(raw)
    if isinstance(raw, float) and math.isnan(raw):
        return "—"
    return format_number(
        float(raw),
        decimals=int(column["decimals"]),
        scale=float(column.get("scale", 1.0)),
        unit=str(column.get("unit", "")),
        absolute=False,
    )


def _inputs_table(results: Path, run: str) -> str:
    """Return the inputs of a run as recorded: name, file, size and SHA-256 (first 16)."""
    inputs = _record(results, run)["inputs"]
    lines = ["| Input | File | Bytes | SHA-256 (first 16) |", "|---|---|---:|---|"]
    for key in sorted(inputs):
        item = inputs[key]
        file = Path(str(item["given"]).replace("\\", "/")).name
        size = reporting_number(int(item["bytes"]), 0, style=EN)
        lines.append(f"| {key} | {file} | {size} | {str(item['sha256'])[:16]} |")
    return "\n".join(lines) + "\n"


def resolve_table(results: Path, name: str, spec: Mapping[str, Any]) -> str:
    """Return one table of the paper as Markdown (``inputs_of = RUN`` lists a run's inputs)."""
    if "inputs_of" in spec:
        return _inputs_table(results, str(spec["inputs_of"]))
    rows = _rows(results, spec)
    if rows.empty:
        raise ValueError(f"{name}: 'where' selects no rows")
    columns = spec["columns"]
    header = "| " + " | ".join(c["header"] for c in columns) + " |"
    rule = "|" + "|".join("---:" if "decimals" in c else "---" for c in columns) + "|"
    body = [
        "| " + " | ".join(_cell(row[c["column"]], c) for c in columns) + " |"
        for _, row in rows.iterrows()
    ]
    return "\n".join([header, rule, *body]) + "\n"


def generate(results: Path, paper: Path) -> dict[str, str]:
    """Return every generated file of the paper: relative path -> content."""
    values: dict[str, str] = {}
    files: dict[str, str] = {}
    for spec_file in sorted((paper / "values").glob("*.toml")):
        spec = tomllib.loads(spec_file.read_text(encoding="utf-8"))
        for name, value in spec.get("values", {}).items():
            if name in values:
                raise ValueError(f"value {name!r} is declared twice")
            values[name] = resolve_value(results, name, value)
        for name, table in spec.get("tables", {}).items():
            files[f"{GENERATED}/{name}.md"] = resolve_table(results, name, table)
    files[f"{GENERATED}/values.json"] = json.dumps(values, indent=1, sort_keys=True) + "\n"
    return files


def substitutions_used(paper: Path) -> set[str]:
    """Return every substitution name used in the paper's Markdown files."""
    used: set[str] = set()
    for page in paper.rglob("*.md"):
        if GENERATED not in page.parts:
            used |= set(SUBSTITUTION.findall(page.read_text(encoding="utf-8")))
    return used


def write_or_check(results: Path, paper: Path, *, check: bool) -> list[str]:
    """Write the generated files, or list the ones that differ from what is on disk."""
    files = generate(results, paper)
    if not check:
        for relative, content in files.items():
            target = paper / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        return []
    differ = []
    for relative, content in files.items():
        target = paper / relative
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            differ.append(relative)
    return differ


def main(argv: Sequence[str] | None = None, *, root: Path | None = None) -> int:
    """Generate (default) or check (``--check``) the paper's numbers and tables."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--check"]):
        print("usage: paper_values.py [--check]", file=sys.stderr)
        return 2
    base = root if root is not None else Path.cwd()
    differ = write_or_check(
        base / "results" / "studies", base / "docs" / "paper", check=args == ["--check"]
    )
    for relative in differ:
        print(f"differs from the records: {relative}")
    return 1 if differ else 0


if __name__ == "__main__":  # pragma: no cover - run by hand with the local study records
    raise SystemExit(main())
