"""The licence and citation files agree with pyproject.toml (design note 6.3c)."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[2]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_licence_is_bsd_3_clause_everywhere() -> None:
    assert PROJECT["license"] == "BSD-3-Clause"
    assert PROJECT["license-files"] == ["LICENSE"]
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("BSD 3-Clause License")
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert re.search(r"^license: BSD-3-Clause$", citation, re.MULTILINE)
    zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert zenodo["license"] == "BSD-3-Clause"


def test_citation_matches_the_project() -> None:
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert re.search(rf'^version: "?{re.escape(PROJECT["version"])}"?$', citation, re.MULTILINE)
    assert re.search(r'^title: "Quant Research Lab"$', citation, re.MULTILINE)
    assert "cff-version: 1.2.0" in citation
    zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert zenodo["title"] == "Quant Research Lab"
    assert zenodo["upload_type"] == "software"
    assert [c["name"] for c in zenodo["creators"]] == ["Zanichelli, Alessandro"]


def test_the_package_may_be_uploaded() -> None:
    assert "Private :: Do Not Upload" not in PROJECT["classifiers"]
    assert PROJECT["name"] == "quant-research-lab"
    assert set(PROJECT["urls"]) >= {"Homepage", "Documentation", "Source"}
