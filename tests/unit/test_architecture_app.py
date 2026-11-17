"""The desktop app imports only qrlab.experiments and qrlab.reporting from the library."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import qrlab_app

APP_ROOT = Path(qrlab_app.__file__).parent
ALLOWED_QRLAB = {"experiments", "reporting"}
# tomli_w: the form writes TOML (12.1b); matplotlib: the interactive charts (12.3b), already a
# dependency of the library.
ALLOWED_THIRD_PARTY = {"PySide6", "pandas", "tomli_w", "matplotlib"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def test_app_imports_only_the_allowed_packages() -> None:
    violations = []
    for module in sorted(APP_ROOT.rglob("*.py")):
        for name in sorted(_imports(module)):
            top, _, rest = name.partition(".")
            if top == "qrlab":
                ok = rest.split(".")[0] in ALLOWED_QRLAB
            else:
                ok = (
                    top in ALLOWED_THIRD_PARTY
                    or top == "qrlab_app"
                    or top in sys.stdlib_module_names
                    or top == "__future__"
                )
            if not ok:
                violations.append(f"{module.relative_to(APP_ROOT)}: {name}")
    assert not violations, "Forbidden imports in qrlab_app:\n" + "\n".join(violations)


def test_the_checker_catches_a_violation(tmp_path: Path) -> None:
    module = tmp_path / "bad.py"
    module.write_text("from qrlab.metrics import sharpe_ratio\nimport numpy\n", encoding="utf-8")
    assert _imports(module) == {"qrlab.metrics", "numpy"}
