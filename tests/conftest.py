"""Shared pytest fixtures.

All randomness in tests flows through the seeded ``rng`` fixture so results are deterministic.
"""

from __future__ import annotations

import os

# Must be set before matplotlib.pyplot is imported anywhere in the test session.
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import pytest

TEST_SEED = 20261028


@pytest.fixture
def rng() -> np.random.Generator:
    """Return a freshly seeded NumPy generator for each test."""
    return np.random.default_rng(TEST_SEED)
