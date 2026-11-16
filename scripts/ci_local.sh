#!/usr/bin/env bash
# Run the steps of .github/workflows/ci.yml on this machine, in order (design note 10.1).
#
# Usage: bash scripts/ci_local.sh CLONE
#
# CLONE is a fresh clone of the repository, never the working folder: a clone holds only
# committed files, as CI does. On Linux, install the Qt system libraries first (see
# docs/project/linux-checks.md). The script stops at the first failing step.
# tests/unit/scripts/test_ci_local.py keeps these commands equal to ci.yml's.
set -euo pipefail
cd "$1"
export TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 # as on a GitHub runner
git log -1 --format="== commit %h %s"
uv --version

# job: checks
for python in 3.11 3.13; do
    echo "== checks, Python $python"
    export UV_PYTHON="$python"
    uv sync --locked
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
    uv run pytest --cov
done

# job: docs
echo "== docs, Python 3.13"
export UV_PYTHON=3.13
uv sync --locked --group docs
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
uv run sphinx-build -W --keep-going -b doctest docs docs/_build/doctest
echo "== every CI step passed"
