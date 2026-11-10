"""Smoke tests: the package installs, imports and exposes typed metadata."""

from __future__ import annotations

import importlib
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pytest

import qrlab

SUBPACKAGES = ["core", "data", "stats", "validation", "metrics", "backtest", "reporting"]


def test_version_matches_installed_metadata() -> None:
    assert qrlab.__version__ == version("quant-research-lab")


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports_and_is_documented(name: str) -> None:
    module = importlib.import_module(f"qrlab.{name}")
    assert module.__doc__ is not None
    assert module.__doc__.strip()


def test_package_ships_py_typed_marker() -> None:
    assert (Path(qrlab.__file__).parent / "py.typed").is_file()


@pytest.mark.parametrize(
    "dependency", ["numpy", "pandas", "scipy", "statsmodels.api", "matplotlib"]
)
def test_core_dependency_importable(dependency: str) -> None:
    importlib.import_module(dependency)


def test_matplotlib_uses_non_interactive_backend() -> None:
    import matplotlib

    assert matplotlib.get_backend().lower() == "agg"


def test_rng_fixture_returns_generator(rng: np.random.Generator) -> None:
    assert isinstance(rng, np.random.Generator)
