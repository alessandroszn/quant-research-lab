"""The build scripts in ``packaging/`` (design note 6.2): build info, notices, run comparison."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import build_info
import compare_runs
import examples_tree
import notices
import pytest
from packaging.utils import canonicalize_name

ROOT = Path(__file__).parents[3]
COMMIT = "0123456789abcdef0123456789abcdef01234567"


# ---------------------------------------------------------------------------- build_info
def test_build_info_from_fixed_inputs() -> None:
    info = build_info.build_info(
        commit=COMMIT,
        status="",
        built=datetime(2026, 11, 13, 11, 30, 15, 999, tzinfo=timezone(timedelta(hours=1))),
        version="0.4.0",
        python="3.13.16",
        packages={"pandas": "2.3.3", "numpy": "2.3.4"},
    )
    assert info == {
        "commit": COMMIT,
        "dirty": False,
        "built": "2026-11-13T10:30:15+00:00",  # converted to UTC, whole seconds
        "version": "0.4.0",
        "python": "3.13.16",
        "packages": {"numpy": "2.3.4", "pandas": "2.3.3"},  # sorted
    }


@pytest.mark.parametrize(
    ("commit", "status", "built", "message"),
    [
        (COMMIT, " M src/qrlab/x.py\n", datetime(2026, 1, 1, tzinfo=UTC), "uncommitted"),
        ("abc", "", datetime(2026, 1, 1, tzinfo=UTC), "40-character"),
        (COMMIT.upper(), "", datetime(2026, 1, 1, tzinfo=UTC), "40-character"),
        (COMMIT, "", datetime(2026, 1, 1), "time zone"),
    ],
)
def test_build_info_refuses(commit: str, status: str, built: datetime, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_info.build_info(
            commit=commit, status=status, built=built, version="0", python="3", packages={}
        )


def test_build_info_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def clean_git(*args: str) -> str:
        return COMMIT + "\n" if args[0] == "rev-parse" else ""

    def dirty_git(*args: str) -> str:
        return COMMIT if args[0] == "rev-parse" else "?? new.txt\n"

    def now() -> datetime:
        return datetime(2026, 11, 13, 10, 0, tzinfo=UTC)

    out = tmp_path / "build-info.json"
    assert build_info.main([str(out)], git=clean_git, now=now) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["commit"] == COMMIT
    assert written["built"] == "2026-11-13T10:00:00+00:00"
    assert written["packages"]["quant-research-lab"] == written["version"]
    assert build_info.main([str(tmp_path / "x.json")], git=dirty_git, now=now) == 1
    assert "uncommitted" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()
    assert build_info.main([]) == 2


def test_git_helper_reads_this_repository() -> None:
    commit = build_info._git("rev-parse", "HEAD").strip()
    assert len(commit) == 40


# ------------------------------------------------------------------------------- notices
def _dist(
    site: Path, name: str, requires: list[str], licences: dict[str, str] | None = None
) -> None:
    info = site / f"{name}-1.0.dist-info"
    info.mkdir(parents=True)
    lines = ["Metadata-Version: 2.4", f"Name: {name}", "Version: 1.0", "License-Expression: MIT"]
    lines += [f"Requires-Dist: {r}" for r in requires]
    (info / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")
    record = [f"{name}-1.0.dist-info/METADATA,,"]
    for relative, text in (licences or {}).items():
        file = info / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        record.append(f"{name}-1.0.dist-info/{relative},,")
    record.append(f"{name}/__init__.py,,")  # not metadata: never read as a licence
    (info / "RECORD").write_text("\n".join(record) + "\n", encoding="utf-8")


@pytest.fixture
def site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    _dist(site, "root", ["alpha", 'beta[fast]; extra == "app"', 'gamma; extra == "other"'])
    _dist(site, "alpha", ['delta; python_version < "3"'], {"licenses/LICENSE": "alpha licence"})
    _dist(site, "beta", ['epsilon; extra == "fast"'], {"COPYING.txt": "beta copying"})
    _dist(site, "epsilon", [], {"LICENSE": "epsilon licence", "NOTICE": "epsilon notice"})
    _dist(site, "tool", ["build-only"], {"LICENSE.md": "tool licence"})  # not followed
    _dist(site, "bare", [])
    return site


def test_bundled_distributions_follow_extras_and_markers(site: Path) -> None:
    found = notices.bundled_distributions("root", {"app"}, ["tool"], path=[str(site)])
    # gamma needs another extra and delta another Python: neither is bundled; root is left out.
    assert [d.metadata["Name"] for d in found] == ["alpha", "beta", "epsilon", "tool"]
    without = notices.bundled_distributions("root", set(), [], path=[str(site)])
    assert [d.metadata["Name"] for d in without] == ["alpha"]


def test_notices_text(site: Path) -> None:
    found = notices.bundled_distributions("root", {"app"}, ["tool"], path=[str(site)])
    assert notices.licence_files(found[2]) == [
        ("LICENSE", "epsilon licence"),
        ("NOTICE", "epsilon notice"),
    ]
    text = notices.notices(found, python_licence="PSF licence")
    assert text.startswith(notices.PREAMBLE)
    order = [text.index(s) for s in ("PSF licence", "alpha 1.0", "beta 1.0", "epsilon 1.0")]
    assert order == sorted(order)
    assert "Declared licence: MIT" in text
    assert "epsilon notice" in text
    assert text.endswith("tool licence\n")
    added = notices.notices(found, python_licence="PSF", added={"beta": [("gpl.txt", "GPL")]})
    assert added.index("beta copying") < added.index("gpl.txt") < added.index("epsilon 1.0")


def test_a_distribution_without_licence_stops_the_build(site: Path) -> None:
    found = notices.bundled_distributions("root", set(), ["bare"], path=[str(site)])
    with pytest.raises(ValueError, match="no licence text for: bare"):
        notices.notices(found, python_licence="PSF")
    reviewed = notices.notices(found, python_licence="PSF", reviewed={"bare": "checked by hand"})
    assert "reviewed licence text" in reviewed
    assert "checked by hand" in reviewed


def test_a_missing_requirement_is_reported(tmp_path: Path) -> None:
    site = tmp_path / "site"
    _dist(site, "root", ["ghost"])
    with pytest.raises(ValueError, match="ghost is required but not installed"):
        notices.bundled_distributions("root", set(), [], path=[str(site)])


def test_the_real_environment_has_every_licence() -> None:
    """The build environment of this repository ships a licence text for every bundled one."""
    found = notices.bundled_distributions(also=[])
    names = {canonicalize_name(d.metadata["Name"]) for d in found}
    assert {"numpy", "pandas", "pyside6-essentials", "pyarrow"} <= names
    assert "quant-research-lab" not in names
    assert "Qt" in notices.notices(found, python_licence="PSF")


def test_notices_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert notices.main([]) == 2
    # PyInstaller is only in the "build" group: leave it out so the test runs everywhere.
    monkeypatch.setattr(notices, "ALSO_SHIPPED", ())
    out = tmp_path / "notices.txt"
    assert notices.main([str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith(notices.PREAMBLE)
    qt = text.index("PySide6_Essentials ")
    assert text.index("GNU LESSER GENERAL PUBLIC LICENSE", qt) < text.index("shiboken6 ")
    assert "GNU GENERAL PUBLIC LICENSE" in text[qt:]
    # Without Python's own licence the notices are incomplete: nothing is written.
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path / "no-python"))
    missing = tmp_path / "missing.txt"
    assert notices.main([str(missing)]) == 1
    assert "Python's licence" in capsys.readouterr().err
    assert not missing.exists()


def test_python_licence_is_found_on_every_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path))
    assert notices.python_licence_path() is None
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    unix = tmp_path / "lib" / version / "LICENSE.txt"
    unix.parent.mkdir(parents=True)
    unix.write_text("PSF", encoding="utf-8")
    assert notices.python_licence_path() == unix  # Linux and macOS
    (tmp_path / "LICENSE.txt").write_text("PSF", encoding="utf-8")
    assert notices.python_licence_path() == tmp_path / "LICENSE.txt"  # Windows


def test_licence_texts_are_the_official_ones() -> None:
    """The LGPL and GPL texts are unchanged copies of https://www.gnu.org/licenses/."""
    expected = {
        "lgpl-3.0.txt": "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118",
        "gpl-3.0.txt": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((notices.LICENCES / name).read_bytes()).hexdigest() == digest


# --------------------------------------------------------------------------- compare_runs
def _run(folder: Path, *, table: str = "a,b\n1,2\n", scalar: float = 0.5) -> None:
    folder.mkdir(parents=True)
    (folder / "t.csv").write_text(table, encoding="utf-8")
    record = {
        "status": "success",
        "error": None,
        "config": {"path": str(folder / "c.toml"), "sha256": "c1"},
        "inputs": {"data": {"resolved": str(folder / "d.csv"), "sha256": "d1"}},
        "seed": None,
        "outputs": {"t.csv": {"tag": "descriptive"}},
        "scalars": {"p": {"value": scalar, "tag": "in_sample"}},
        "code": {"frozen": "frozen" in str(folder)},
        "started": str(folder),
        "finished": str(folder),
    }
    (folder / "record.json").write_text(json.dumps(record), encoding="utf-8")


def test_identical_runs_agree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(tmp_path / "source" / "demo")
    _run(tmp_path / "frozen" / "demo")  # different paths, times and code block: ignored
    assert compare_runs.compare_runs(tmp_path / "source", tmp_path / "frozen") == []
    assert compare_runs.main([str(tmp_path / "source"), str(tmp_path / "frozen")]) == 0
    assert capsys.readouterr().out == "identical\n"


def test_differences_are_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _run(a / "demo")
    _run(b / "demo", table="a,b\n1,2.0000000000000004\n", scalar=0.5000000000000001)
    _run(a / "only-a")
    _run(b / "only-b")
    problems = compare_runs.compare_runs(a, b)
    assert problems == [
        f"only-a: only in {a}",
        f"only-b: only in {b}",
        "demo: scalars differs: {'p': {'value': 0.5, 'tag': 'in_sample'}} != "
        "{'p': {'value': 0.5000000000000001, 'tag': 'in_sample'}}",
        "demo: t.csv differs",
    ]
    assert compare_runs.main([str(a), str(b)]) == 1
    assert "t.csv differs" in capsys.readouterr().out
    assert compare_runs.compare_runs(tmp_path / "none", tmp_path / "none") == ["no runs to compare"]
    assert compare_runs.main([]) == 2


# -------------------------------------------------------------------------- examples_tree
def test_examples_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    configs = examples_tree.examples_tree(ROOT, tmp_path / "tree")
    names = [c.name for c in configs]
    assert names == sorted(p.name for p in (ROOT / "configs" / "experiments").glob("example_*"))
    assert all(c.parent == tmp_path / "tree" / "ws" / "configs" for c in configs)
    for folder in examples_tree.SUPPORT_FOLDERS:
        assert (tmp_path / "tree" / "ws" / folder).is_dir()
    assert (tmp_path / "tree" / "examples" / "data" / "asset_returns.csv").is_file()
    with pytest.raises(ValueError, match="already exists"):
        examples_tree.examples_tree(ROOT, tmp_path / "tree")
    empty = tmp_path / "empty-repo"
    (empty / "configs" / "experiments").mkdir(parents=True)
    with pytest.raises(ValueError, match="no example configs"):
        examples_tree.examples_tree(empty, tmp_path / "other")
    shutil.rmtree(tmp_path / "tree")
    assert examples_tree.main([str(ROOT), str(tmp_path / "tree")]) == 0
    assert len(capsys.readouterr().out.splitlines()) == len(configs)
    assert examples_tree.main([]) == 2
