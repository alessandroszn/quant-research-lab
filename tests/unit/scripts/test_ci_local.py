"""scripts/ci_local.sh runs the same steps as the CI workflow (design note 10.1).

The workflow is read as text, without a YAML parser: only its ``run:`` lines, its jobs and its
Python versions matter here, and they are one line each.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[3]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
SCRIPT = (ROOT / "scripts" / "ci_local.sh").read_text(encoding="utf-8")
GUIDE = (ROOT / "docs" / "project" / "linux-checks.md").read_text(encoding="utf-8")
APT = "sudo apt-get update && sudo apt-get install -y "


def _ci_jobs() -> dict[str, str]:
    """Each job of ci.yml with its text, from its two-space-indented name to the next one."""
    body = CI[CI.index("\njobs:\n") :]
    parts = re.split(r"^  ([\w-]+):\n", body, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _ci_runs(job: str) -> list[str]:
    return re.findall(r"^\s+run: (.+)$", _ci_jobs()[job], flags=re.MULTILINE)


def _script_section(job: str) -> list[str]:
    """Return the script's commands after ``# job: <job>``, up to the next job, without echoes."""
    section = SCRIPT.split(f"# job: {job}\n")[1].split("# job: ")[0]
    lines = (line.strip() for line in section.splitlines())
    return [line for line in lines if line and not line.startswith(("#", "echo "))]


def test_the_jobs_are_the_ones_the_script_knows() -> None:
    assert list(_ci_jobs()) == ["checks", "docs"]


def test_the_checks_job_runs_the_same_commands_in_order() -> None:
    expected = [run for run in _ci_runs("checks") if "apt-get" not in run]
    commands = [c for c in _script_section("checks") if c.startswith("uv ")]
    assert commands == expected


def test_the_docs_job_runs_the_same_commands_in_order() -> None:
    commands = [c for c in _script_section("docs") if c.startswith("uv ")]
    assert commands == _ci_runs("docs")


def test_the_python_versions_match() -> None:
    matrix = re.search(r"python-version: \[(.+)\]", _ci_jobs()["checks"])
    assert matrix is not None
    versions = [v.strip().strip('"') for v in matrix.group(1).split(",")]
    assert f"for python in {' '.join(versions)}; do" in _script_section("checks")
    docs = re.search(r'python-version: "(.+)"', _ci_jobs()["docs"])
    assert docs is not None
    assert f"export UV_PYTHON={docs.group(1)}" in _script_section("docs")


def test_the_guide_installs_the_same_system_libraries() -> None:
    ci_apt = [run for run in _ci_runs("checks") if "apt-get" in run]
    assert len(ci_apt) == 1
    ci_packages = set(ci_apt[0].removeprefix(APT).split())
    guide_line = next(line.strip() for line in GUIDE.splitlines() if line.strip().startswith(APT))
    assert set(guide_line.removeprefix(APT).split()) == ci_packages | {"git"}


def test_the_script_stops_at_the_first_failure() -> None:
    assert SCRIPT.startswith("#!/usr/bin/env bash\n")
    assert "\nset -euo pipefail\n" in SCRIPT
