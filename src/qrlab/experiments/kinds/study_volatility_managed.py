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

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.data.ken_french import parse_ken_french
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import boolean, day, number, whole
from qrlab.experiments.kinds._studies import (
    bootstrap_settings,
    describe,
    ken_french_provenance,
    names,
    numbers,
)
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
    factors = names(parameters, "factors")
    unknown = sorted(set(factors) - set(FACTORS))
    if unknown:
        raise ValidationError(f"unknown factors {unknown}; known: {list(FACTORS)}")
    start, end = day(parameters, "start"), day(parameters, "end")
    if start >= end:
        raise ValidationError("start must be before end")
    caps = numbers(parameters, "leverage_caps", allow_inf=True)
    if any(not c > 0 for c in caps):
        raise ValidationError("leverage_caps must be positive (inf for no cap)")
    costs = numbers(parameters, "costs_bp", allow_inf=False)
    if any(c < 0 for c in costs):
        raise ValidationError("costs_bp must be >= 0")
    significance = number(parameters, "significance")
    if not 0.0 < significance < 1.0:
        raise ValidationError("significance must be in (0, 1)")
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
        bootstrap=bootstrap_settings(parameters),
    )


def _load(context: RunContext, family: str) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    frames = []
    facts = []
    for frequency, suffix in ((Frequency.DAILY, "daily"), (Frequency.MONTHLY, "monthly")):
        name = f"{family}_{suffix}"
        path = context.inputs[name]
        provenance = ken_french_provenance(path, INPUTS[name])
        frames.append(parse_ken_french(path.read_bytes(), provenance, frequency=frequency).data)
        facts.append(describe(provenance))
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
