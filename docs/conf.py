"""Sphinx configuration of the Quant Research Lab documentation (design note 6.3b).

Build from the repository root:

    uv sync --locked --group docs
    uv run sphinx-build -W --keep-going -b html docs docs/_build/html
    uv run sphinx-build -W --keep-going -b doctest docs docs/_build/doctest

The build never needs the network. Links to the NumPy, pandas and SciPy documentation
(intersphinx) are only added when ``QRLAB_DOCS_INTERSPHINX=1``, as in the release build.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

project = "Quant Research Lab"
author = "Alessandro Zanichelli"
copyright = "2026, Alessandro Zanichelli"
release = importlib.metadata.version("quant-research-lab")
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.doctest",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
]
if os.environ.get("QRLAB_DOCS_INTERSPHINX") == "1":  # pragma: no cover - release builds only
    extensions.append("sphinx.ext.intersphinx")
    intersphinx_mapping = {
        "python": ("https://docs.python.org/3", None),
        "numpy": ("https://numpy.org/doc/stable", None),
        "pandas": ("https://pandas.pydata.org/docs", None),
        "scipy": ("https://docs.scipy.org/doc/scipy", None),
    }

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
exclude_patterns = ["_build", "api/public-api.txt", "paper/_generated"]

myst_enable_extensions = ["colon_fence", "dollarmath", "deflist", "substitution"]
# Every number of the working paper comes from the study records (design note 6.3d).
_PAPER_VALUES = ROOT / "docs" / "paper" / "_generated" / "values.json"
myst_substitutions = (
    json.loads(_PAPER_VALUES.read_text(encoding="utf-8")) if _PAPER_VALUES.is_file() else {}
)
myst_heading_anchors = 3

# The docstrings are NumPy style; type hints are shown in the signature, not repeated.
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_use_rtype = False
autodoc_typehints = "signature"
autodoc_member_order = "bysource"
autodoc_default_options = {"members": True, "imported-members": True, "show-inheritance": True}
autosummary_generate = False

doctest_global_setup = """
import pandas as pd
import numpy as np
"""

html_theme = "pydata_sphinx_theme"
html_title = f"Quant Research Lab {release}"
html_theme_options = {
    "navigation_with_keys": False,
    "show_toc_level": 2,
    "footer_start": ["copyright"],
    "footer_end": ["sphinx-version"],
}
html_static_path: list[str] = []

# The working paper as a PDF (built locally with LaTeX; not in CI). Design note 6.3d.
latex_engine = "pdflatex"
latex_documents = [
    (
        "paper/index",
        "qrlab-working-paper.tex",
        "What survives? Four reproducible studies of portfolio rules under real-time "
        "implementation, costs and multiple testing",
        "Alessandro Zanichelli",
        "howto",
    )
]
latex_elements = {"papersize": "a4paper", "pointsize": "11pt", "printindex": ""}
