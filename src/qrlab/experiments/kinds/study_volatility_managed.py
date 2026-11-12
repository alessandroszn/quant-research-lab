"""Experiment kind ``study_volatility_managed``: study 1 on Ken French factor files.

Inputs: the six Ken French zip files, unchanged (``ff3_daily``, ``ff3_monthly``, ``ff5_daily``,
``ff5_monthly``, ``mom_daily``, ``mom_monthly``). When a file sits in the raw store, its
``.provenance.json`` sidecar is read and its SHA-256 checked; otherwise the provenance is the
local file. Mkt-RF, SMB and HML come from the three-factor files, RMW and CMA from the
five-factor files, Mom from the momentum files.

Monthly factor returns come from the monthly files and realised variances from the daily files,
as in Moreira and Muir (2017). The signal lag is one month. In-sample results (full-sample scale)
are tagged ``in_sample``; real-time results ``out_of_sample``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.data.errors import IntegrityError
from qrlab.data.ken_french import SOURCE, TERMS, parse_ken_french
from qrlab.data.provenance import Provenance
from qrlab.experiments.config import file_sha256, require_keys
from qrlab.experiments.kinds._params import boolean, day, number, table, whole
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.experiments.runner import configurations_tried
from qrlab.reporting.html import render_html
from qrlab.studies.volatility_managed import (
    BootstrapSettings,
    InSampleResult,
    OutOfSampleResult,
    best_deflated_sharpe,
    in_sample_spanning,
    in_sample_table,
    inverse_variance_signal,
    out_of_sample_comparison,
    out_of_sample_table,
    realized_variance,
)
from qrlab.studies.volatility_managed_report import build_volatility_managed_report

__all__ = ["FACTORS", "INPUTS", "KIND"]

PERIODS_PER_YEAR = 12  # monthly factor files
SIGNAL_LAG = 1  # months (design note 5.3, study 1)

INPUTS: Mapping[str, str] = {
    "ff3_daily": "F-F_Research_Data_Factors_daily",
    "ff3_monthly": "F-F_Research_Data_Factors",
    "ff5_daily": "F-F_Research_Data_5_Factors_2x3_daily",
    "ff5_monthly": "F-F_Research_Data_5_Factors_2x3",
    "mom_daily": "F-F_Momentum_Factor_daily",
    "mom_monthly": "F-F_Momentum_Factor",
}
"""Input name -> Ken French dataset."""

FACTORS: Mapping[str, str] = {
    "Mkt-RF": "ff3",
    "SMB": "ff3",
    "HML": "ff3",
    "RMW": "ff5",
    "CMA": "ff5",
    "Mom": "mom",
}
"""Factor -> file family it is read from."""

_PARAMETERS = (
    "factors",
    "start",
    "end",
    "demean_daily",
    "hac_lags",
    "burn_in_months",
    "leverage_caps",
    "costs_bp",
    "significance",
    "bootstrap",
)
_SIDECAR = ".provenance.json"


@dataclass(frozen=True)
class _Parameters:
    factors: tuple[str, ...]
    start: date
    end: date
    demean: bool
    hac_lags: int
    burn_in: int
    caps: tuple[float, ...]
    costs: tuple[float, ...]  # per unit traded, decimals
    significance: float
    bootstrap: BootstrapSettings


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    factors = _strings(parameters, "factors")
    unknown = sorted(set(factors) - set(FACTORS))
    if unknown:
        raise ValidationError(f"unknown factors {unknown}; known: {list(FACTORS)}")
    start, end = day(parameters, "start"), day(parameters, "end")
    if start >= end:
        raise ValidationError("start must be before end")
    caps = _numbers(parameters, "leverage_caps", allow_inf=True)
    if any(not c > 0 for c in caps):
        raise ValidationError("leverage_caps must be positive (inf for no cap)")
    costs = _numbers(parameters, "costs_bp", allow_inf=False)
    if any(c < 0 for c in costs):
        raise ValidationError("costs_bp must be >= 0")
    significance = number(parameters, "significance")
    if not 0.0 < significance < 1.0:
        raise ValidationError("significance must be in (0, 1)")
    boot = table(
        parameters,
        "bootstrap",
        required={"mean_block_length", "n_resamples", "confidence"},
        optional=set(),
    )
    return _Parameters(
        factors=factors,
        start=start,
        end=end,
        demean=boolean(parameters, "demean_daily"),
        hac_lags=whole(parameters, "hac_lags", minimum=0),
        burn_in=whole(parameters, "burn_in_months", minimum=2),
        caps=caps,
        costs=tuple(c / 1e4 for c in costs),
        significance=significance,
        bootstrap=BootstrapSettings(
            mean_block_length=number(boot, "mean_block_length"),
            n_resamples=whole(boot, "n_resamples", minimum=1),
            confidence=number(boot, "confidence"),
        ),
    )


def _strings(parent: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = parent[key]
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise ValidationError(f"{key} must be a non-empty list of names")
    if len(set(value)) != len(value):
        raise ValidationError(f"{key} has duplicates")
    return tuple(value)


def _numbers(parent: Mapping[str, object], key: str, *, allow_inf: bool) -> tuple[float, ...]:
    value = parent[key]
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{key} must be a non-empty list of numbers")
    out = []
    for item in value:
        if (
            type(item) not in (int, float)
            or math.isnan(item)
            or (math.isinf(item) and not allow_inf)
        ):
            raise ValidationError(f"{key} must contain numbers{' or inf' if allow_inf else ''}")
        out.append(float(item))
    if len(set(out)) != len(out):
        raise ValidationError(f"{key} has duplicates")
    return tuple(out)


def _provenance(path: Path, dataset: str) -> Provenance:
    """Provenance from the raw store's sidecar when present, else from the local file."""
    sidecar = path.with_name(path.name + _SIDECAR)
    sha = file_sha256(path)
    if sidecar.is_file():
        stored = Provenance.from_json(sidecar.read_text(encoding="utf-8"))
        if stored.sha256 != sha:
            raise IntegrityError(f"{path.name}: SHA-256 differs from its provenance sidecar")
        if stored.source != SOURCE or stored.dataset != dataset:
            raise ValidationError(
                f"{path.name}: provenance says {stored.source}/{stored.dataset}, "
                f"expected {SOURCE}/{dataset}"
            )
        return stored
    stat = path.stat()
    return Provenance(
        source=SOURCE,
        dataset=dataset,
        url=f"file:{path.name}",
        retrieved_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        sha256=sha,
        size_bytes=stat.st_size,
        terms=TERMS,
    )


def _load(context: RunContext, family: str) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    frames = []
    facts = []
    for frequency, suffix in ((Frequency.DAILY, "daily"), (Frequency.MONTHLY, "monthly")):
        name = f"{family}_{suffix}"
        path = context.inputs[name]
        provenance = _provenance(path, INPUTS[name])
        frames.append(parse_ken_french(path.read_bytes(), provenance, frequency=frequency).data)
        facts.append(
            f"{provenance.dataset}: {provenance.url}, retrieved "
            f"{provenance.retrieved_at.date().isoformat()}, SHA-256 {provenance.sha256[:12]}"
        )
    return frames[0], frames[1], facts


def _window(series: pd.Series, start: date, end: date, name: str) -> pd.Series:
    """Restrict to the months from ``start`` to ``end`` and trim leading/trailing NaN.

    NaN inside the window raises: a gap in the data is never filled or skipped silently.
    """
    first = pd.Timestamp(start).replace(day=1)
    last = pd.Timestamp(end) + pd.offsets.MonthEnd(0)
    window = series.loc[(series.index >= first) & (series.index <= last)]
    valid = window.dropna()
    if valid.empty:
        raise ValidationError(f"{name}: no data between {start} and {end}")
    trimmed = window.loc[valid.index[0] : valid.index[-1]]
    if trimmed.isna().any():
        raise ValidationError(f"{name}: missing values inside the sample window")
    return trimmed.astype("float64")


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    rng = np.random.default_rng(int(context.seed))  # type: ignore[arg-type]
    families = sorted({FACTORS[f] for f in p.factors})
    loaded = {family: _load(context, family) for family in families}
    in_sample: dict[str, InSampleResult] = {}
    out: list[tuple[str, OutOfSampleResult]] = []
    weights: dict[str, pd.Series] = {}
    for factor in p.factors:
        daily_frame, monthly_frame, _ = loaded[FACTORS[factor]]
        daily = _window(daily_frame[factor], p.start, p.end, f"{factor} daily")
        monthly = _window(monthly_frame[factor], p.start, p.end, f"{factor} monthly")
        signal = inverse_variance_signal(realized_variance(daily, demean=p.demean), lag=SIGNAL_LAG)
        in_sample[factor] = in_sample_spanning(
            monthly, signal, hac_lags=p.hac_lags, periods_per_year=PERIODS_PER_YEAR
        )
        for cap in p.caps:
            for cost in p.costs:
                result = out_of_sample_comparison(
                    monthly,
                    signal,
                    burn_in=p.burn_in,
                    cap=cap,
                    cost_per_unit=cost,
                    hac_lags=p.hac_lags,
                    periods_per_year=PERIODS_PER_YEAR,
                    bootstrap=p.bootstrap,
                    rng=rng,
                )
                out.append((factor, result))
                weights[f"{factor} cap {cap:g}"] = result.weights
    config = context.config
    tried = configurations_tried(config.output_dir.parent, config.name, including=config.hash)
    deflated = best_deflated_sharpe(out, configurations=tried)
    in_table = in_sample_table(in_sample, significance=p.significance)
    out_table = out_of_sample_table(out, significance=p.significance)
    facts = [
        ("Sample window", f"{p.start.isoformat()} to {p.end.isoformat()}"),
        (
            "Specification",
            f"signal lag {SIGNAL_LAG} month; demeaned daily returns: {p.demean}; HAC lags "
            f"{p.hac_lags}; burn-in {p.burn_in} months; caps {list(p.caps)}; costs (bp) "
            f"{[round(c * 1e4, 6) for c in p.costs]}",
        ),
        ("Configurations tried", str(tried)),
        *(("Data", line) for family in families for line in loaded[family][2]),
    ]
    report = build_volatility_managed_report(
        title=f"Study 1: volatility-managed factors ({config.name})",
        hypothesis=config.hypothesis,
        facts=facts,
        in_sample=in_table,
        out_of_sample=out_table,
        deflated=deflated,
        significance=p.significance,
    )
    scalars: dict[str, Tagged] = {
        "configurations_tried": Tagged(float(tried), "descriptive"),
        "in_sample_alpha_rejections_holm": Tagged(
            float((in_table["alpha_holm"] <= p.significance).sum()), "in_sample"
        ),
        "out_of_sample_rejections_holm": Tagged(
            float((out_table["holm"] <= p.significance).sum()), "out_of_sample"
        ),
    }
    if deflated is not None:
        label, dsr, n_trials = deflated
        scalars["dsr_best_variant"] = Tagged(label, "out_of_sample")
        scalars["dsr_probability"] = Tagged(dsr.probability, "out_of_sample")
        scalars["dsr_trials"] = Tagged(float(n_trials), "out_of_sample")
    return ExperimentOutput(
        tables={
            "in_sample": Tagged(in_table, "in_sample"),
            "out_of_sample": Tagged(out_table, "out_of_sample"),
            "weights": Tagged(pd.DataFrame(weights), "out_of_sample"),
        },
        scalars=scalars,
        report_html=render_html(report),
    )


KIND = ExperimentKind(
    name="study_volatility_managed",
    description="Study 1: volatility-managed factors, in sample and in real time after costs",
    inputs=tuple(INPUTS),
    needs_seed=True,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
)
