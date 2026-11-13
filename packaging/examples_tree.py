"""Copy the example configs and their synthetic data into a fresh folder.

Usage: ``python packaging/examples_tree.py REPOSITORY DESTINATION``

Layout of ``DESTINATION`` (the configs' relative paths keep working unchanged):

- ``ws/configs/example_*.toml``: the example experiments; ``ws`` is also a valid app workspace;
- ``ws/checks``, ``ws/csv_mappings``, ``ws/scenarios``: the files they refer to as ``../...``;
- ``examples/data``: the synthetic inputs they refer to as ``../../examples/data/...``;
- ``results/``: where the runs write (``../../results/...``).

It prints one config path per line, for the build workflow to run.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

__all__ = ["SUPPORT_FOLDERS", "examples_tree", "main"]

SUPPORT_FOLDERS = ("checks", "csv_mappings", "scenarios")


def examples_tree(repository: Path, destination: Path) -> list[Path]:
    """Build the tree; return the config paths, sorted. ``destination`` must not exist."""
    repo, dest = Path(repository), Path(destination)
    if dest.exists():
        raise ValueError(f"{dest} already exists")
    configs = sorted((repo / "configs" / "experiments").glob("example_*.toml"))
    if not configs:
        raise ValueError(f"no example configs under {repo / 'configs' / 'experiments'}")
    (dest / "ws" / "configs").mkdir(parents=True)
    copies = [Path(shutil.copy2(c, dest / "ws" / "configs" / c.name)) for c in configs]
    for folder in SUPPORT_FOLDERS:
        shutil.copytree(repo / "configs" / folder, dest / "ws" / folder)
    shutil.copytree(repo / "examples" / "data", dest / "examples" / "data")
    return copies


def main(argv: Sequence[str] | None = None) -> int:
    """Build the tree and print its config paths."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: examples_tree.py REPOSITORY DESTINATION", file=sys.stderr)
        return 2
    for path in examples_tree(Path(args[0]), Path(args[1])):
        print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover - run as a script by the build workflow
    raise SystemExit(main())
