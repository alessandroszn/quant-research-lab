"""Validation shared by the risk models: simple-return frames and portfolio weights."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy, validate_frame


def asset_returns(
    returns: pd.DataFrame, *, kind: ReturnKind, missing: NanPolicy, min_obs: int
) -> tuple[pd.DataFrame, int]:
    """Validate simple asset returns; return the frame and the number of dropped rows."""
    if kind is not ReturnKind.SIMPLE:
        raise ValidationError("risk models need simple returns (portfolio return is w'r)")
    if missing not in (NanPolicy.RAISE, NanPolicy.DROP):
        raise ValidationError("missing must be NanPolicy.RAISE or NanPolicy.DROP")
    frame = validate_frame(returns, nan_policy=missing, name="returns")
    if frame.shape[1] == 0:
        raise ValidationError("returns need at least one asset column")
    if len(frame) < min_obs:
        raise ValidationError(f"returns need at least {min_obs} observations, got {len(frame)}")
    return frame, len(returns) - len(frame)


def portfolio_weights(weights: pd.Series, assets: pd.Index) -> np.ndarray:
    """Return finite weights ordered like ``assets``; labels must match exactly."""
    if not isinstance(weights, pd.Series):
        raise ValidationError("weights must be a pandas Series indexed by asset")
    if weights.index.has_duplicates:
        raise ValidationError("weights have duplicated asset labels")
    if set(weights.index) != set(assets):
        missing = sorted(map(str, set(assets) - set(weights.index)))
        extra = sorted(map(str, set(weights.index) - set(assets)))
        raise ValidationError(
            f"weight labels must match the assets (missing {missing}, extra {extra})"
        )
    values = weights.reindex(assets).to_numpy(dtype=np.float64)
    if not all(math.isfinite(v) for v in values):
        raise ValidationError("weights must be finite")
    return values
