r"""Corrections for testing many hypotheses at once.

With sorted p-values :math:`p_{(1)}\le\dots\le p_{(m)}`:

- **Holm (1979)**, family-wise error rate under any dependence:
  :math:`\tilde p_{(i)}=\max_{j\le i}\min\{1,(m-j+1)p_{(j)}\}`;
- **Benjamini-Hochberg (1995)**, false discovery rate under independence or positive
  dependence: :math:`\tilde p_{(i)}=\min_{j\ge i}\min\{1,m\,p_{(j)}/j\}`;
- **Benjamini-Yekutieli (2001)**, false discovery rate under any dependence: BH with
  :math:`m` replaced by :math:`m\,c(m)`, :math:`c(m)=\sum_{k=1}^m 1/k`.

A hypothesis is rejected when its adjusted p-value is at most :math:`\alpha`. Not rejecting is
not evidence that there is no effect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError

__all__ = ["Correction", "CorrectionResult", "adjust_pvalues"]


class Correction(Enum):
    """Multiple-testing correction."""

    HOLM = "holm"
    BENJAMINI_HOCHBERG = "benjamini_hochberg"
    BENJAMINI_YEKUTIELI = "benjamini_yekutieli"


@dataclass(frozen=True)
class CorrectionResult:
    """Adjusted p-values and rejections, in the input order."""

    pvalues: pd.Series
    adjusted: pd.Series
    rejected: pd.Series
    method: Correction
    alpha: float

    @property
    def m(self) -> int:
        """Return the number of hypotheses."""
        return len(self.pvalues)


def adjust_pvalues(pvalues: pd.Series, *, method: Correction, alpha: float) -> CorrectionResult:
    """Adjust ``pvalues`` (labelled by hypothesis) for multiple testing."""
    if not isinstance(method, Correction):
        raise ValidationError(f"method must be a Correction, got {method!r}")
    if type(alpha) is not float or not 0.0 < alpha < 1.0:
        raise ValidationError(f"alpha must be a float strictly between 0 and 1, got {alpha!r}")
    given: object = pvalues
    if not isinstance(given, pd.Series) or given.empty:
        raise ValidationError("pvalues must be a non-empty pandas Series")
    if pvalues.index.has_duplicates:
        raise ValidationError("hypothesis labels must be unique")
    p = pvalues.to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(p)) or (p < 0).any() or (p > 1).any():
        raise ValidationError("p-values must be finite and in [0, 1]")
    m = len(p)
    order = np.argsort(p, kind="stable")
    ranked = p[order]
    ranks = np.arange(1, m + 1)
    if method is Correction.HOLM:
        adjusted_sorted = np.maximum.accumulate(np.minimum(1.0, (m - ranks + 1) * ranked))
    else:
        factor = m * (_harmonic(m) if method is Correction.BENJAMINI_YEKUTIELI else 1.0)
        raw = np.minimum(1.0, factor * ranked / ranks)
        adjusted_sorted = np.minimum.accumulate(raw[::-1])[::-1]
    adjusted = np.empty(m)
    adjusted[order] = adjusted_sorted
    adjusted_series = pd.Series(adjusted, index=pvalues.index, name="adjusted")
    return CorrectionResult(
        pvalues=pvalues.astype("float64"),
        adjusted=adjusted_series,
        rejected=(adjusted_series <= alpha).rename("rejected"),
        method=method,
        alpha=float(alpha),
    )


def _harmonic(m: int) -> float:
    return math.fsum(1.0 / k for k in range(1, m + 1))
