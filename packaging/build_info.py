"""Write ``build-info.json`` for a frozen build; refuse a dirty working tree.

Usage: ``python packaging/build_info.py OUTPUT_FILE``

The file records the commit, the build time (UTC), the Python version, the project version and
every installed distribution with its version. The runner of a frozen program reads the commit
from it (``qrlab.experiments.runner``), so it must describe the shipped code exactly: a build
from a tree with uncommitted changes is refused.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["build_info", "installed_packages", "main"]


def build_info(
    *,
    commit: str,
    status: str,
    built: datetime,
    version: str,
    python: str,
    packages: Mapping[str, str],
) -> dict[str, object]:
    """Return the build record; ``status`` is the output of ``git status --porcelain``.

    Raises
    ------
    ValueError
        If the tree has uncommitted changes, the commit is not a full hash or ``built`` has no
        time zone.
    """
    if status.strip():
        raise ValueError(f"the working tree has uncommitted changes:\n{status.strip()}")
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError(f"commit must be a 40-character git hash, got {commit!r}")
    if built.tzinfo is None:
        raise ValueError("built must carry a time zone")
    return {
        "commit": commit,
        "dirty": False,
        "built": built.astimezone(UTC).isoformat(timespec="seconds"),
        "version": version,
        "python": python,
        "packages": dict(sorted(packages.items())),
    }


def installed_packages() -> dict[str, str]:
    """Every installed distribution (lower-case name) with its version."""
    return {
        dist.metadata["Name"].lower(): dist.version for dist in importlib.metadata.distributions()
    }


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, timeout=60
    ).stdout


def main(
    argv: Sequence[str] | None = None,
    *,
    git: Callable[..., str] = _git,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Write the file named on the command line; 1 and a message for a dirty tree."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: build_info.py OUTPUT_FILE", file=sys.stderr)
        return 2
    try:
        info = build_info(
            commit=git("rev-parse", "HEAD").strip(),
            status=git("status", "--porcelain"),
            built=now(),
            version=importlib.metadata.version("quant-research-lab"),
            python=platform.python_version(),
            packages=installed_packages(),
        )
    except ValueError as exc:
        print(f"build_info: {exc}", file=sys.stderr)
        return 1
    Path(args[0]).write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - run as a script by the build workflow
    raise SystemExit(main())
