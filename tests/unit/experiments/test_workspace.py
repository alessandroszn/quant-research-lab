"""Workspace listings: configs, runs and raw files on hand-built folders."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qrlab.core.errors import QrlabError
from qrlab.data.provenance import Provenance
from qrlab.data.store import RawStore
from qrlab.experiments import load_config
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.workspace import (
    WORKSPACE_FOLDERS,
    config_template,
    create_workspace,
    list_configs,
    list_raw_files,
    list_runs,
)

ROOT = Path(__file__).parents[3]
PROJECTION = ROOT / "configs" / "experiments" / "example_projection.toml"


def test_create_workspace(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws")
    assert sorted(p.name for p in root.iterdir()) == sorted(WORKSPACE_FOLDERS)
    create_workspace(root)  # idempotent
    file = tmp_path / "file.txt"
    file.write_text("x")
    with pytest.raises(QrlabError, match="is a file"):
        create_workspace(file)


def test_list_configs_reports_validity(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws")
    good = PROJECTION.read_text(encoding="utf-8")
    (root / "configs" / "b_good.toml").write_text(good, encoding="utf-8")
    (root / "configs" / "sub").mkdir()
    bad = good.replace("paths = ", "paths_typo = ")
    (root / "configs" / "sub" / "a_bad.toml").write_text(bad, encoding="utf-8")
    (root / "configs" / "c_broken.toml").write_text("not = [toml", encoding="utf-8")
    entries = list_configs(root, kinds=KINDS)
    assert [e.path.name for e in entries] == ["b_good.toml", "c_broken.toml", "a_bad.toml"]
    good_entry, broken, invalid = entries
    assert good_entry.valid
    assert good_entry.kind == "projection"
    assert good_entry.error is None
    assert not broken.valid
    assert broken.kind is None
    assert "invalid TOML" in str(broken.error)
    assert not invalid.valid
    assert invalid.kind == "projection"
    assert "paths" in str(invalid.error)
    assert list_configs(tmp_path / "missing", kinds=KINDS) == []


def _record(folder: Path, name: str, finished: str, status: str = "success") -> None:
    folder.mkdir(parents=True)
    record = {
        "experiment": {"name": name, "kind": "projection", "hypothesis": "h"},
        "config": {"sha256": "a" * 64},
        "status": status,
        "started": finished,
        "finished": finished,
        "configurations_tried": 2,
        "error": None if status == "success" else "ValidationError: x",
    }
    (folder / "record.json").write_text(json.dumps(record), encoding="utf-8")


def test_list_runs_newest_first_and_skips_broken(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws")
    _record(root / "results" / "old", "old", "2026-11-10T10:00:00+00:00")
    _record(root / "results" / "x" / "new", "new", "2026-11-12T10:00:00+00:00", "failure")
    (root / "results" / "broken").mkdir()
    (root / "results" / "broken" / "record.json").write_text("{", encoding="utf-8")
    runs = list_runs(root)
    assert [r.name for r in runs] == ["new", "old"]
    assert runs[0].status == "failure"
    assert runs[0].error == "ValidationError: x"
    assert runs[1].configurations_tried == 2
    assert runs[1].error is None
    assert list_runs(tmp_path / "missing") == []


def _store(root: Path, dataset: str, content: bytes, when: datetime) -> None:
    provenance = Provenance(
        source="ecb",
        dataset=dataset,
        url="https://example.org/file.csv",
        retrieved_at=when,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="test terms",
    )
    RawStore(root / "data").put(content, provenance)


def test_list_raw_files_with_ages(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws")
    _store(root, "fx", b"v1", datetime(2026, 11, 1, tzinfo=UTC))
    _store(root, "fx", b"v2", datetime(2026, 11, 10, tzinfo=UTC))
    _store(root, "estr", b"e", datetime(2026, 11, 11, tzinfo=UTC))
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    files = list_raw_files(root, now=now)
    assert [(f.dataset, f.age_days, f.latest) for f in files] == [
        ("estr", 1, True),
        ("fx", 11, False),
        ("fx", 2, True),
    ]
    assert files[0].terms == "test terms"
    assert files[0].size_bytes == 1
    assert list_raw_files(tmp_path / "missing", now=now) == []
    with pytest.raises(QrlabError, match="timezone-aware"):
        list_raw_files(root, now=datetime(2026, 11, 12))


def test_config_template_lists_every_key(tmp_path: Path) -> None:
    kind = KINDS["backtest"]
    text = config_template(kind)
    path = tmp_path / "new.toml"
    path.write_text(text, encoding="utf-8")
    config = load_config(path)
    assert config.kind == "backtest"
    assert config.seed is None
    for name in kind.inputs:
        assert f"{name} = " in text
    for name in kind.parameters:
        assert f"# {name} = FILL-IN" in text
    assert "seed = 1" in config_template(KINDS["projection"])


def test_list_runs_skips_staging_and_replaced_folders(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws")
    _record(root / "results" / "demo", "demo", "2026-11-10T10:00:00+00:00")
    _record(root / "results" / ".demo.partial", "demo", "2026-11-11T10:00:00+00:00")
    _record(root / "results" / ".demo.old", "demo", "2026-11-09T10:00:00+00:00")
    _record(root / "results" / ".hidden" / "inner", "inner", "2026-11-12T10:00:00+00:00")
    _record(root / "results" / "set" / "a.b", "dotted", "2026-11-13T10:00:00+00:00")
    runs = list_runs(root)
    assert [(r.name, r.output_dir.name) for r in runs] == [("dotted", "a.b"), ("demo", "demo")]
