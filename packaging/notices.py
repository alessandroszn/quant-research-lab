"""Write ``THIRD_PARTY_NOTICES.txt``: the licence texts of everything a frozen build ships.

Usage: ``python packaging/notices.py OUTPUT_FILE``

The bundled distributions are the dependency closure of ``quant-research-lab`` with the
``app`` and ``parquet`` extras (markers evaluated on the build machine), plus PyInstaller,
whose bootloader starts the program (its own dependencies are build tools and are not
shipped). Each one must ship a licence file in its metadata; one that does not stops the
build, unless it is on :data:`REVIEWED` with a text checked by hand. Python's own licence
comes first.
"""

from __future__ import annotations

import importlib.metadata
import sys
from collections.abc import Iterable, Mapping, Sequence
from importlib.metadata import Distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

__all__ = [
    "PREAMBLE",
    "REVIEWED",
    "bundled_distributions",
    "licence_files",
    "main",
    "notices",
    "python_licence_path",
]

ROOT = "quant-research-lab"
EXTRAS = frozenset({"app", "parquet"})
ALSO_SHIPPED = ("pyinstaller",)  # the bootloader is part of every executable

REVIEWED: Mapping[str, str] = {}
"""Distribution -> licence text checked by hand, for one that ships no licence file."""

LICENCES = Path(__file__).parent / "licences"
ADDED_TEXTS: Mapping[str, tuple[str, ...]] = {
    "pyside6-essentials": ("lgpl-3.0.txt", "gpl-3.0.txt"),
    "shiboken6": ("lgpl-3.0.txt", "gpl-3.0.txt"),
}
"""Distribution -> texts in ``packaging/licences`` shipped with it.

The PySide6 wheels carry only Qt's commercial licence file, but they are used under the LGPL,
which requires shipping the LGPL-3.0 and GPL-3.0 texts. Both come unchanged from
https://www.gnu.org/licenses/ (SHA-256 in ``packaging/README.md``).
"""

PREAMBLE = """\
Quant Research Lab - third-party notices

Quant Research Lab itself: no licence has been granted yet; all rights are reserved by the
author. The program is research analytics, not investment advice.

It ships the software listed below, each under its own licence, reproduced in full.

Qt and PySide6 (Qt for Python) are used under the GNU Lesser General Public License v3 (LGPL).
They are dynamically linked: their libraries are the separate files in the program's
_internal/PySide6 folder, and you may replace them with your own build of the same Qt
version. The Qt source code is available from https://download.qt.io/ and the PySide6
source from https://code.qt.io/.
"""

_LICENCE_PREFIXES = ("licen", "copying", "notice")


def _find(name: str, path: Sequence[str] | None) -> Distribution:
    found = list(
        importlib.metadata.distributions(name=name)
        if path is None
        else importlib.metadata.distributions(name=name, path=list(path))
    )
    if not found:
        raise ValueError(f"{name} is required but not installed")
    return found[0]


def bundled_distributions(
    root: str = ROOT,
    extras: Iterable[str] = EXTRAS,
    also: Iterable[str] = ALSO_SHIPPED,
    *,
    path: Sequence[str] | None = None,
) -> list[Distribution]:
    """Return ``root``'s dependency closure with ``extras``, plus ``also``, sorted by name.

    ``root`` itself is left out: its own licence is stated in :data:`PREAMBLE`. The ``also``
    distributions are added without their dependencies.
    """
    found: dict[str, Distribution] = {}
    done: set[tuple[str, frozenset[str]]] = set()
    queue: list[tuple[str, frozenset[str]]] = [(root, frozenset(extras))]
    for name in also:
        found[canonicalize_name(name)] = _find(name, path)
    while queue:
        name, active = queue.pop()
        key = canonicalize_name(name)
        if (key, active) in done:
            continue
        done.add((key, active))
        dist = _find(name, path)
        found[key] = dist
        for line in dist.requires or []:
            requirement = Requirement(line)
            marker = requirement.marker
            if marker is None or any(marker.evaluate({"extra": e}) for e in {"", *active}):
                queue.append((requirement.name, frozenset(requirement.extras)))
    found.pop(canonicalize_name(root), None)
    return [found[k] for k in sorted(found)]


def licence_files(dist: Distribution) -> list[tuple[str, str]]:
    """Return ``(file name, text)`` for every licence-like file in the distribution's metadata."""
    texts = []
    for file in sorted(dist.files or [], key=str):
        if ".dist-info" not in str(file) or not file.name.lower().startswith(_LICENCE_PREFIXES):
            continue
        located = Path(str(dist.locate_file(file)))
        texts.append((file.name, located.read_text(encoding="utf-8", errors="replace")))
    return texts


def notices(
    dists: Iterable[Distribution],
    *,
    python_licence: str,
    reviewed: Mapping[str, str] = REVIEWED,
    added: Mapping[str, Sequence[tuple[str, str]]] | None = None,
) -> str:
    """Return the full notices text; raise if a distribution has no licence text at all.

    ``added`` maps a distribution to extra ``(name, text)`` pairs shipped with it.
    """
    rule = "=" * 78
    parts = [PREAMBLE, rule, f"Python {sys.version.split()[0]}", "-" * 78, python_licence]
    missing = []
    for dist in dists:
        name = dist.metadata["Name"]
        texts = licence_files(dist)
        if not texts and canonicalize_name(name) in reviewed:
            texts = [("reviewed licence text", reviewed[canonicalize_name(name)])]
        if not texts:
            missing.append(name)
            continue
        texts += list((added or {}).get(canonicalize_name(name), ()))
        meta = dist.metadata.json
        declared = str(meta.get("license_expression") or meta.get("license") or "")
        parts += [
            "",
            rule,
            f"{name} {dist.version}",
            f"Declared licence: {declared or 'see below'}",
        ]
        for file_name, text in texts:
            parts += ["-" * 78, file_name, "", text.strip()]
    if missing:
        raise ValueError(f"no licence text for: {', '.join(sorted(missing))}")
    return "\n".join(parts).rstrip() + "\n"


def python_licence_path() -> Path | None:
    """Python's own LICENSE.txt: at the top of a Windows install, under ``lib/`` elsewhere."""
    base = Path(sys.base_prefix)
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for candidate in (base / "LICENSE.txt", base / "lib" / version / "LICENSE.txt"):
        if candidate.is_file():
            return candidate
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Write the notices to the file named on the command line."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: notices.py OUTPUT_FILE", file=sys.stderr)
        return 2
    python_licence = python_licence_path()
    try:
        if python_licence is None:
            raise ValueError(f"Python's licence is not under {sys.base_prefix}")
        added = {
            dist: [(f, (LICENCES / f).read_text(encoding="utf-8")) for f in files]
            for dist, files in ADDED_TEXTS.items()
        }
        text = notices(
            bundled_distributions(also=ALSO_SHIPPED),
            python_licence=python_licence.read_text(encoding="utf-8"),
            added=added,
        )
    except ValueError as exc:
        print(f"notices: {exc}", file=sys.stderr)
        return 1
    Path(args[0]).write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - run as a script by the build workflow
    raise SystemExit(main())
