"""Enforce the package layering so that dependencies only point downward.

Example of what this catches: ``metrics`` importing from ``backtest`` would couple a
pure function of returns to simulation logic, and ``core`` importing anything would
create cycles. The rule is checked statically by parsing every module's imports.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import qrlab

PACKAGE_ROOT = Path(qrlab.__file__).parent

# Allowed internal dependencies for each subpackage (besides itself).
ALLOWED: dict[str, set[str]] = {
    "core": set(),
    "data": {"core"},
    # Documented exception (design note 1.3): instruments sits in layer 1 next to data but loads
    # files through data's raw store and provenance. data never imports instruments.
    "instruments": {"core", "data"},
    "stats": {"core"},
    "portfolio": {"core", "data", "instruments", "metrics"},
    "lookthrough": {"core", "data", "instruments", "metrics", "portfolio"},
    "scenarios": {"core", "data", "instruments", "metrics", "risk", "portfolio"},
    "checks": {
        "core",
        "data",
        "instruments",
        "stats",
        "metrics",
        "risk",
        "portfolio",
        "lookthrough",
    },
    "metrics": {"core", "stats"},
    "risk": {"core", "stats", "metrics"},
    "validation": {"core"},
    "backtest": {"core", "data", "metrics", "validation"},
    "reporting": {
        "core",
        "data",
        "instruments",
        "stats",
        "metrics",
        "risk",
        "validation",
        "portfolio",
        "checks",
        "lookthrough",
        "scenarios",
        "backtest",
    },
}


def _internal_imports(path: Path, root: Path = PACKAGE_ROOT) -> set[str]:
    """Return the ``qrlab`` subpackages imported by a module (absolute or relative)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Package containing this module, e.g. ["qrlab", "metrics"] for qrlab/metrics/sharpe.py.
    package = ["qrlab", *path.relative_to(root).parent.parts]
    found: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = (node.module or "").split(".")
            else:
                base = package[: len(package) - (node.level - 1)]
                if node.module:
                    base = [*base, *node.module.split(".")]
            if base == ["qrlab"]:
                # `from qrlab import backtest` / `from .. import backtest`: names are subpackages.
                names = [f"qrlab.{alias.name}" for alias in node.names]
            else:
                names = [".".join(base)]
        for name in names:
            parts = name.split(".")
            if parts[0] == "qrlab" and len(parts) > 1:
                found.add(parts[1])
    return found


def test_every_subpackage_has_a_layering_rule() -> None:
    subpackages = {p.name for p in PACKAGE_ROOT.iterdir() if (p / "__init__.py").is_file()}
    assert subpackages == set(ALLOWED)


@pytest.mark.parametrize("subpackage", sorted(ALLOWED))
def test_imports_respect_layering(subpackage: str) -> None:
    violations: list[str] = []
    for module in sorted((PACKAGE_ROOT / subpackage).rglob("*.py")):
        illegal = _internal_imports(module) - ALLOWED[subpackage] - {subpackage}
        if illegal:
            violations.append(f"{module.relative_to(PACKAGE_ROOT)} -> {sorted(illegal)}")
    assert not violations, "Layering violations:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import qrlab.backtest", {"backtest"}),
        ("from qrlab.backtest import x", {"backtest"}),
        # Regression: these two forms were missed by the first version of the parser.
        ("from qrlab import backtest", {"backtest"}),
        ("from .. import reporting", {"reporting"}),
        ("from ..reporting import y", {"reporting"}),
        ("from ..reporting.figures import z", {"reporting"}),
        ("from . import helpers", {"metrics"}),
        ("from .helpers import h", {"metrics"}),
        ("import numpy as np", set()),
        # Importing from the root package is reported too: subpackages must not depend on it.
        ("from qrlab import __version__", {"__version__"}),
    ],
)
def test_import_parser(tmp_path: Path, source: str, expected: set[str]) -> None:
    """Guard the guard: absolute and relative imports must resolve to the right subpackage."""
    fake_pkg = tmp_path / "metrics"
    fake_pkg.mkdir()
    module = fake_pkg / "mod.py"
    module.write_text(source + "\n")
    assert _internal_imports(module, root=tmp_path) == expected


def test_import_parser_handles_nested_modules(tmp_path: Path) -> None:
    nested = tmp_path / "metrics" / "risk"
    nested.mkdir(parents=True)
    module = nested / "var.py"
    module.write_text("from .. import sharpe\nfrom ...backtest import engine\n")
    assert _internal_imports(module, root=tmp_path) == {"metrics", "backtest"}
