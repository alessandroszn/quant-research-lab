"""Shared readers for kinds that work on a returns CSV: format, covariance and weights."""

from __future__ import annotations

import io
from collections.abc import Mapping

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.data.user_csv import PriceType
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import boolean, choice, number, table, text
from qrlab.risk.covariance import (
    CovarianceEstimate,
    ewma_covariance,
    ledoit_wolf_covariance,
    sample_covariance,
)

__all__ = [
    "ADVICE",
    "COVARIANCE_ESTIMATORS",
    "PRICE_RETURNS",
    "covariance_spec",
    "estimate_covariance",
    "price_type",
    "read_returns",
    "returns_format",
    "returns_notice",
    "weights",
]

COVARIANCE_ESTIMATORS = ("sample", "ewma", "ledoit_wolf")

ADVICE = "Research analytics, not investment advice."
PRICE_RETURNS = (
    "Returns declared as price returns (dividends excluded): return levels are understated by "
    "about the dividend yield; volatilities and correlations are barely affected."
)
_DECLARED = {"total_return": PriceType.TOTAL_RETURN, "price": PriceType.PRICE}


def price_type(parameters: Mapping[str, object], key: str) -> PriceType:
    """Read the declared price type of a returns file: ``"total_return"`` or ``"price"``.

    ``"nav"`` is refused: a NAV return includes the income of an accumulating fund but not of a
    distributing one, so it does not say which of the two the returns are. The declaration only
    labels the data; nothing is converted.
    """
    if parameters.get(key) == "nav":
        raise ValidationError(
            f"{key} = 'nav' does not say whether income is included: declare 'total_return' "
            "for an accumulating fund (income stays in the NAV) or 'price' for a distributing "
            "fund (income is paid out)"
        )
    return _DECLARED[choice(parameters, key, set(_DECLARED))]


def returns_notice(caveats: str | None, declared: PriceType | None) -> str | None:
    """Join a kind's caveats, the price-return sentence when it applies, and :data:`ADVICE`.

    ``declared`` is ``None`` when the run reads no returns file whose type was declared. With
    no caveats and no price returns there is no notice (``None``).
    """
    sentences = [caveats] if caveats else []
    if declared is PriceType.PRICE:
        sentences.append(PRICE_RETURNS)
    return " ".join([*sentences, ADVICE]) if sentences else None


def returns_format(parameters: Mapping[str, object], key: str = "returns_format") -> dict[str, str]:
    """Read ``{date_column, date_format, delimiter, decimal_separator}``."""
    fmt = table(
        parameters,
        key,
        required={"date_column", "date_format", "delimiter", "decimal_separator"},
        optional=set(),
    )
    return {k: text(fmt, k) if k != "delimiter" else str(fmt[k]) for k in fmt}


def read_returns(content: bytes, fmt: Mapping[str, str]) -> pd.DataFrame:
    """Read a returns CSV with an explicit format (no guessing)."""
    frame = pd.read_csv(
        io.BytesIO(content),
        sep=fmt["delimiter"],
        decimal=fmt["decimal_separator"],
        dtype={fmt["date_column"]: str},
    )
    if fmt["date_column"] not in frame.columns:
        raise ValidationError(f"no date column {fmt['date_column']!r} in the returns file")
    index = pd.to_datetime(frame.pop(fmt["date_column"]), format=fmt["date_format"])
    frame.index = pd.DatetimeIndex(index, name="date")
    return frame.astype("float64")


def covariance_spec(parameters: Mapping[str, object], key: str = "covariance") -> dict[str, object]:
    """Read ``{estimator, decay?, demean?}``; ``decay`` and ``demean`` only for ``ewma``."""
    spec = parameters[key]
    if not isinstance(spec, dict):
        raise ValidationError(f"{key} must be a table")
    name = choice(spec, "estimator", set(COVARIANCE_ESTIMATORS))
    extra = {"decay", "demean"} if name == "ewma" else set()
    require_keys(spec, required={"estimator", *extra}, optional=set(), where=key)
    out: dict[str, object] = {"estimator": name}
    if name == "ewma":
        out["decay"] = number(spec, "decay")
        out["demean"] = boolean(spec, "demean")
    return out


def estimate_covariance(returns: pd.DataFrame, spec: Mapping[str, object]) -> CovarianceEstimate:
    """Estimate the covariance of simple returns (missing values raise)."""
    common = {"kind": ReturnKind.SIMPLE, "missing": NanPolicy.RAISE}
    if spec["estimator"] == "sample":
        return sample_covariance(returns, **common)  # type: ignore[arg-type]
    if spec["estimator"] == "ewma":
        return ewma_covariance(
            returns,
            decay=float(spec["decay"]),  # type: ignore[arg-type]
            demean=bool(spec["demean"]),
            **common,  # type: ignore[arg-type]
        )
    return ledoit_wolf_covariance(returns, **common)  # type: ignore[arg-type]


def weights(table_value: Mapping[str, object], assets: list[str]) -> pd.Series:
    """Read an already parsed ``{asset = weight}`` table covering exactly ``assets``."""
    given = {str(k): number(table_value, k) for k in table_value}
    if set(given) != set(assets):
        raise ValidationError(
            "weights must cover exactly the assets of the returns file: missing "
            f"{sorted(set(assets) - set(given))}, unknown {sorted(set(given) - set(assets))}"
        )
    return pd.Series(given).reindex(assets).astype("float64")
