"""Compare two results folders run from the same configs: the frozen build against the source.

Usage: ``python packaging/compare_runs.py RESULTS_A RESULTS_B``

Each results folder holds one sub-folder per run with its ``record.json``. Two runs agree when
they have the same status, error, input and config hashes, output files with the same tags and
**identical bytes**, and identical scalars. What legitimately differs is ignored: the start and
end times, the code-version block (frozen or not) and the absolute paths in the record.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

__all__ = ["compare_runs", "main"]


def _record(folder: Path) -> dict[str, Any]:
    record: dict[str, Any] = json.loads((folder / "record.json").read_text(encoding="utf-8"))
    return record


def _comparable(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": record["status"],
        "error": record["error"],
        "config_sha256": record["config"]["sha256"],
        "inputs": {k: v["sha256"] for k, v in record["inputs"].items()},
        "seed": record["seed"],
        "outputs": record["outputs"],
        "scalars": record["scalars"],
    }


def compare_runs(a: Path, b: Path) -> list[str]:
    """Return every difference between the runs under ``a`` and ``b`` (empty: identical)."""
    runs_a = {p.parent.name for p in Path(a).glob("*/record.json")}
    runs_b = {p.parent.name for p in Path(b).glob("*/record.json")}
    problems = [f"{name}: only in {a}" for name in sorted(runs_a - runs_b)]
    problems += [f"{name}: only in {b}" for name in sorted(runs_b - runs_a)]
    if not runs_a | runs_b:
        problems.append("no runs to compare")
    for name in sorted(runs_a & runs_b):
        left, right = Path(a) / name, Path(b) / name
        first, second = _comparable(_record(left)), _comparable(_record(right))
        for key in first:
            if first[key] != second[key]:
                problems.append(f"{name}: {key} differs: {first[key]!r} != {second[key]!r}")
        for output in sorted(set(first["outputs"]) & set(second["outputs"])):
            if (left / output).read_bytes() != (right / output).read_bytes():
                problems.append(f"{name}: {output} differs")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Print the differences; 0 when the two folders agree."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: compare_runs.py RESULTS_A RESULTS_B", file=sys.stderr)
        return 2
    problems = compare_runs(Path(args[0]), Path(args[1]))
    for problem in problems:
        print(problem)
    if not problems:
        print("identical")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover - run as a script by the build workflow
    raise SystemExit(main())
