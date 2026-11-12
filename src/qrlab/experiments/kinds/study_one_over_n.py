"""Experiment kind ``study_one_over_n``: study 2 on Ken French portfolio files.

Inputs: the daily and monthly files of the 10 industry portfolios and of the 25 size and
book-to-market portfolios, plus the monthly three-factor file for the risk-free rate. Returns are
the value-weighted sections; market weights are number of firms x average firm size. When a file
sits in the raw store, its provenance sidecar is read and its SHA-256 checked.

Every result is out of sample (rolling estimation windows, execution one trading day after each
month-end decision) and tagged ``out_of_sample``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.data.ken_french import (
    AVERAGE_FIRM_SIZE,
    AVERAGE_MARKET_CAP,
    NUMBER_OF_FIRMS,
    VALUE_WEIGHTED_DAILY,
    VALUE_WEIGHTED_MONTHLY,
    parse_ken_french,
    parse_ken_french_table,
)
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import day, number, whole
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
from qrlab.studies.one_over_n import (
    STRATEGIES,
    Comparison,
    Performance,
    best_deflated_sharpe,
    compare,
    comparison_table,
    market_weights,
    monthly_excess_returns,
    monthly_net_excess,
    pair_table,
    performance,
    performance_table,
    rolling_targets,
    run_targets,
)
from qrlab.studies.one_over_n_report import build_one_over_n_report
from qrlab.studies.volatility_managed import BootstrapSettings

__all__ = ["DATASETS", "INPUTS", "KIND", "PAIRS", "SIZE_SECTIONS"]

INPUTS: Mapping[str, str] = {
    "ind10_daily": "10_Industry_Portfolios_daily",
    "ind10_monthly": "10_Industry_Portfolios",
    "p25_daily": "25_Portfolios_5x5_Daily",
    "p25_monthly": "25_Portfolios_5x5",
    "ff3_monthly": "F-F_Research_Data_Factors",
}
"""Input name -> Ken French dataset."""

DATASETS: Mapping[str, tuple[str, str]] = {
    "industries_10": ("ind10_daily", "ind10_monthly"),
    "size_bm_25": ("p25_daily", "p25_monthly"),
}
"""Universe -> (daily input, monthly input)."""

SIZE_SECTIONS: Mapping[str, str] = {
    "industries_10": AVERAGE_FIRM_SIZE,
    "size_bm_25": AVERAGE_MARKET_CAP,
}
"""Universe -> title of its average-size section (the files name it differently)."""

PAIRS = (("minvar_lw", "minvar_sample"), ("maxsharpe_bl", "maxsharpe_sample"))
"""H2: (robust, sample-estimate) strategy pairs."""

_PARAMETERS = (
    "datasets",
    "start",
    "end",
    "windows",
    "strategies",
    "costs_bp",
    "bl_risk_aversion",
    "ceq_risk_aversion",
    "hac_lags",
    "significance",
    "bootstrap",
)


@dataclass(frozen=True)
class _Parameters:
    datasets: tuple[str, ...]
    start: date
    end: date
    windows: tuple[int, ...]
    strategies: tuple[str, ...]
    costs: tuple[float, ...]  # per unit traded, decimals
    bl_risk_aversion: float
    ceq_risk_aversion: float
    hac_lags: int
    significance: float
    bootstrap: BootstrapSettings


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    datasets = names(parameters, "datasets")
    unknown = sorted(set(datasets) - set(DATASETS))
    if unknown:
        raise ValidationError(f"unknown datasets {unknown}; known: {list(DATASETS)}")
    strategies = names(parameters, "strategies")
    unknown = sorted(set(strategies) - set(STRATEGIES))
    if unknown:
        raise ValidationError(f"unknown strategies {unknown}; known: {list(STRATEGIES)}")
    if "ew" not in strategies or len(strategies) < 2:
        raise ValidationError("strategies must include the 1/N benchmark 'ew' and one other")
    start, end = day(parameters, "start"), day(parameters, "end")
    if start >= end:
        raise ValidationError("start must be before end")
    windows = numbers(parameters, "windows", allow_inf=False)
    if any(w != int(w) or w < 2 for w in windows):
        raise ValidationError("windows must be whole numbers of months >= 2")
    costs = numbers(parameters, "costs_bp", allow_inf=False)
    if any(c < 0 for c in costs):
        raise ValidationError("costs_bp must be >= 0")
    positive = {}
    for key in ("bl_risk_aversion", "ceq_risk_aversion"):
        positive[key] = number(parameters, key)
        if not positive[key] > 0:
            raise ValidationError(f"{key} must be positive")
    significance = number(parameters, "significance")
    if not 0.0 < significance < 1.0:
        raise ValidationError("significance must be in (0, 1)")
    return _Parameters(
        datasets=datasets,
        start=start,
        end=end,
        windows=tuple(int(w) for w in windows),
        strategies=strategies,
        costs=tuple(c / 1e4 for c in costs),
        bl_risk_aversion=positive["bl_risk_aversion"],
        ceq_risk_aversion=positive["ceq_risk_aversion"],
        hac_lags=whole(parameters, "hac_lags", minimum=0),
        significance=significance,
        bootstrap=bootstrap_settings(parameters),
    )


@dataclass(frozen=True)
class _Universe:
    daily: pd.DataFrame
    excess: pd.DataFrame
    market: pd.DataFrame


def _months(frame: pd.DataFrame, start: date, end: date, name: str) -> pd.DataFrame:
    """Restrict to the months from ``start`` to ``end``; missing values inside raise."""
    first = pd.Timestamp(start).replace(day=1)
    last = pd.Timestamp(end) + pd.offsets.MonthEnd(0)
    window = frame.loc[(frame.index >= first) & (frame.index <= last)]
    if window.empty:
        raise ValidationError(f"{name}: no data between {start} and {end}")
    if window.isna().any().any():
        raise ValidationError(f"{name}: missing values inside the sample window")
    return window.astype("float64")


def _load(context: RunContext, p: _Parameters) -> tuple[dict[str, _Universe], pd.Series, list[str]]:
    facts = []

    def read(name: str) -> tuple[bytes, object]:
        path = context.inputs[name]
        provenance = ken_french_provenance(path, INPUTS[name])
        facts.append(describe(provenance))
        return path.read_bytes(), provenance

    content, prov = read("ff3_monthly")
    rf = parse_ken_french(content, prov, frequency=Frequency.MONTHLY).data["RF"]  # type: ignore[arg-type]
    universes = {}
    for dataset in p.datasets:
        daily_name, monthly_name = DATASETS[dataset]
        content, prov = read(daily_name)
        daily = parse_ken_french(
            content,
            prov,  # type: ignore[arg-type]
            frequency=Frequency.DAILY,
            section=VALUE_WEIGHTED_DAILY,
        ).data
        content, prov = read(monthly_name)
        monthly = parse_ken_french(
            content,
            prov,  # type: ignore[arg-type]
            frequency=Frequency.MONTHLY,
            section=VALUE_WEIGHTED_MONTHLY,
        ).data
        tables = [
            parse_ken_french_table(
                content,
                prov,  # type: ignore[arg-type]
                frequency=Frequency.MONTHLY,
                section=title,
            )
            for title in (NUMBER_OF_FIRMS, SIZE_SECTIONS[dataset])
        ]
        returns = _months(monthly, p.start, p.end, f"{dataset} monthly")
        universes[dataset] = _Universe(
            daily=_months(daily, p.start, p.end, f"{dataset} daily"),
            excess=monthly_excess_returns(returns, rf),
            market=market_weights(*(t.reindex(returns.index) for t in tables)),
        )
    return universes, rf, facts


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    rng = np.random.default_rng(int(context.seed))  # type: ignore[arg-type]
    universes, rf, facts = _load(context, p)
    results: dict[tuple[str, int, float, str], Performance] = {}
    series: dict[tuple[str, int, float, str], pd.Series] = {}
    for dataset, universe in universes.items():
        excess = universe.excess
        if len(excess) <= max(p.windows):
            raise ValidationError(f"{dataset}: fewer months than the longest window plus one")
        first = excess.index[max(p.windows) - 1]
        for window in p.windows:
            for strategy in p.strategies:
                targets = rolling_targets(
                    excess,
                    strategy=strategy,
                    window=window,
                    market=universe.market,
                    bl_risk_aversion=p.bl_risk_aversion,
                    first=first,
                )
                for cost in p.costs:
                    result = run_targets(universe.daily, targets.weights, cost=cost)
                    net = monthly_net_excess(result, rf)
                    turnover = sum(e.turnover for e in result.executions) / len(net)
                    key = (dataset, window, cost, strategy)
                    series[key] = net
                    results[key] = performance(
                        net,
                        turnover=turnover,
                        ceq_risk_aversion=p.ceq_risk_aversion,
                        fallbacks=targets.fallbacks,
                    )
    comparisons: dict[tuple[str, int, float, str], Comparison] = {}
    pairs: dict[tuple[str, int, float, str, str], Comparison] = {}
    for dataset, window, cost, strategy in series:
        if strategy != "ew":
            comparisons[(dataset, window, cost, strategy)] = _compare(
                series, (dataset, window, cost), strategy, "ew", p, rng
            )
    for dataset in p.datasets:
        for window in p.windows:
            for cost in p.costs:
                for robust, sample in PAIRS:
                    if robust in p.strategies and sample in p.strategies:
                        pairs[(dataset, window, cost, robust, sample)] = _compare(
                            series, (dataset, window, cost), robust, sample, p, rng
                        )
    config = context.config
    tried = configurations_tried(config.output_dir.parent, config.name, including=config.hash)
    deflated = best_deflated_sharpe(
        {f"{d} | M={w} | {c * 1e4:g} bp | {s}": v for (d, w, c, s), v in series.items()},
        configurations=tried,
    )
    perf_table = performance_table(results)
    test_table = comparison_table(comparisons, significance=p.significance)
    pair_frame = pair_table(pairs, significance=p.significance) if pairs else None
    report = build_one_over_n_report(
        title=f"Study 2: 1/N against optimised portfolios ({config.name})",
        hypothesis=config.hypothesis,
        facts=[
            ("Sample window", f"{p.start.isoformat()} to {p.end.isoformat()}"),
            (
                "Specification",
                f"windows {list(p.windows)} months (rolling); strategies {list(p.strategies)}; "
                f"costs (bp) {[round(c * 1e4, 6) for c in p.costs]}; execution one trading day "
                f"after month end; BL delta {p.bl_risk_aversion:g}, tau = 1/window; CEQ gamma "
                f"{p.ceq_risk_aversion:g}; HAC lags {p.hac_lags}",
            ),
            ("Configurations tried", str(tried)),
            *(("Data", line) for line in facts),
        ],
        performance=perf_table,
        comparisons=test_table,
        pairs=pair_frame,
        deflated=deflated,
        significance=p.significance,
    )
    significant = test_table["holm"] <= p.significance
    scalars: dict[str, Tagged] = {
        "configurations_tried": Tagged(float(tried), "descriptive"),
        "better_than_1n_holm": Tagged(
            float((significant & (test_table["z_hac"] > 0)).sum()), "out_of_sample"
        ),
        "worse_than_1n_holm": Tagged(
            float((significant & (test_table["z_hac"] < 0)).sum()), "out_of_sample"
        ),
    }
    if pair_frame is not None:
        scalars["robust_better_holm"] = Tagged(
            float(((pair_frame["holm"] <= p.significance) & (pair_frame["z_hac"] > 0)).sum()),
            "out_of_sample",
        )
    if deflated is not None:  # pragma: no branch - _parse requires two strategies
        label, dsr, n_trials = deflated
        scalars["dsr_best_variant"] = Tagged(label, "out_of_sample")
        scalars["dsr_probability"] = Tagged(dsr.probability, "out_of_sample")
        scalars["dsr_trials"] = Tagged(float(n_trials), "out_of_sample")
    tables = {
        "performance": Tagged(perf_table, "out_of_sample"),
        "against_1n": Tagged(test_table, "out_of_sample"),
    }
    if pair_frame is not None:
        tables["robust_pairs"] = Tagged(pair_frame, "out_of_sample")
    return ExperimentOutput(tables=tables, scalars=scalars, report_html=render_html(report))


def _compare(
    series: Mapping[tuple[str, int, float, str], pd.Series],
    group: tuple[str, int, float],
    candidate: str,
    benchmark: str,
    p: _Parameters,
    rng: np.random.Generator,
) -> Comparison:
    return compare(
        series[(*group, candidate)],
        series[(*group, benchmark)],
        hac_lags=p.hac_lags,
        bootstrap=p.bootstrap,
        rng=rng,
        ceq_risk_aversion=p.ceq_risk_aversion,
    )


KIND = ExperimentKind(
    name="study_one_over_n",
    description="Study 2: 1/N against optimised portfolios, out of sample after costs",
    inputs=tuple(INPUTS),
    needs_seed=True,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
)
