"""Experiment kind ``study_factor_zoo``: study 3 on Open Source Asset Pricing files.

Inputs: ``ls_returns`` (``PredictorLSretWide.parquet``, needs ``qrlab[parquet]``) and
``signal_doc`` (``SignalDoc.csv``). Predictors are the signals with ``Cat.Signal = Predictor``
whose ``Predictability in OP`` is one of ``categories``. Returns after ``end`` are not used.

Original-sample tests are tagged ``in_sample``; post-sample and post-publication results, the
decay regression and the later composites ``out_of_sample``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.data.open_asset_pricing import (
    SOURCE,
    TERMS,
    parse_long_short_returns,
    parse_signal_doc,
)
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import day, number, whole
from qrlab.experiments.kinds._studies import describe, names, raw_provenance
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.experiments.runner import configurations_tried
from qrlab.reporting.html import render_html
from qrlab.studies.factor_zoo import (
    composites,
    decay_regression,
    long_panel,
    predictor_tests,
    significance_counts,
)
from qrlab.studies.factor_zoo_report import build_factor_zoo_report

__all__ = ["INPUTS", "KIND"]

INPUTS: Mapping[str, str] = {"ls_returns": "long_short_returns", "signal_doc": "signal_doc"}
"""Input name -> OSAP dataset."""

_PARAMETERS = (
    "categories",
    "end",
    "hac_lags",
    "min_months",
    "hlz_threshold",
    "significance",
)


@dataclass(frozen=True)
class _Parameters:
    categories: tuple[str, ...]
    end: date
    hac_lags: int
    min_months: int
    hlz_threshold: float
    significance: float


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    significance = number(parameters, "significance")
    if not 0.0 < significance < 1.0:
        raise ValidationError("significance must be in (0, 1)")
    threshold = number(parameters, "hlz_threshold")
    if not threshold > 0:
        raise ValidationError("hlz_threshold must be positive")
    return _Parameters(
        categories=names(parameters, "categories"),
        end=day(parameters, "end"),
        hac_lags=whole(parameters, "hac_lags", minimum=0),
        min_months=whole(parameters, "min_months", minimum=3),
        hlz_threshold=threshold,
        significance=significance,
    )


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    facts = []
    files = {}
    for name, dataset in INPUTS.items():
        path = context.inputs[name]
        provenance = raw_provenance(path, source=SOURCE, dataset=dataset, terms=TERMS)
        facts.append(describe(provenance))
        files[name] = (path.read_bytes(), provenance)
    doc = parse_signal_doc(*files["signal_doc"])
    returns = parse_long_short_returns(*files["ls_returns"]).data
    returns = returns.loc[returns.index <= pd.Timestamp(p.end) + pd.offsets.MonthEnd(0)]
    selected = doc[
        (doc["Cat.Signal"] == "Predictor") & doc["Predictability in OP"].isin(p.categories)
    ]
    if selected.empty:
        raise ValidationError(f"no predictors in categories {list(p.categories)}")
    panel = long_panel(returns, selected)
    tests = {
        phase: predictor_tests(panel, phase=phase, hac_lags=p.hac_lags, min_months=p.min_months)
        for phase in ("in_sample", "post_sample", "post_publication")
    }
    counts_in = significance_counts(
        tests["in_sample"], significance=p.significance, hlz_threshold=p.hlz_threshold
    )
    counts_pub = significance_counts(
        tests["post_publication"], significance=p.significance, hlz_threshold=p.hlz_threshold
    )
    decay = decay_regression(panel)
    composite = composites(panel, hac_lags=p.hac_lags)
    gaps = panel.groupby("predictor")["gaps"].first()
    config = context.config
    tried = configurations_tried(config.output_dir.parent, config.name, including=config.hash)
    report = build_factor_zoo_report(
        title=f"Study 3: the factor zoo ({config.name})",
        hypothesis=config.hypothesis,
        facts=[
            (
                "Universe",
                f"{len(selected)} predictors with Predictability in OP in {list(p.categories)}",
            ),
            (
                "Specification",
                f"returns up to {p.end.isoformat()}; Newey-West lags {p.hac_lags}; at least "
                f"{p.min_months} months per tested phase; HLZ threshold t > "
                f"{p.hlz_threshold:g}; significance {p.significance:g}; post-publication from "
                "January after the publication year",
            ),
            (
                "Missing months inside series",
                f"{int(gaps.sum())} in all, in {int((gaps > 0).sum())} predictors (left out)",
            ),
            ("Configurations tried", str(tried)),
            *(("Data", line) for line in facts),
        ],
        counts_in_sample=counts_in,
        counts_post_publication=counts_pub,
        decay=decay,
        composites=composite,
    )
    by_predictor = (
        tests["in_sample"]
        .add_prefix("in_")
        .join(tests["post_sample"].add_prefix("post_sample_"), how="outer")
        .join(tests["post_publication"].add_prefix("post_pub_"), how="outer")
        .join(selected[["Authors", "Year", "SampleStartYear", "SampleEndYear"]], how="left")
    )
    decay_frame = pd.DataFrame([vars(decay)])
    later = composite.drop(index="in_sample")
    scalars: dict[str, Tagged] = {
        "configurations_tried": Tagged(float(tried), "descriptive"),
        "predictors": Tagged(float(len(selected)), "descriptive"),
        "decay_post_sample": Tagged(decay.decay_post_sample, "out_of_sample"),
        "decay_post_publication": Tagged(decay.decay_post_publication, "out_of_sample"),
        "p_post_publication": Tagged(decay.p_post_publication, "out_of_sample"),
    }
    # decay_regression has already required in-sample and post-publication months.
    means = composite["mean"].astype("float64")
    scalars["composite_post_publication_mean"] = Tagged(
        float(means["post_publication"]), "out_of_sample"
    )
    tables = {
        "in_sample_tests": Tagged(tests["in_sample"], "in_sample"),
        "in_sample_counts": Tagged(counts_in, "in_sample"),
        "post_publication_counts": Tagged(counts_pub, "out_of_sample"),
        "by_predictor": Tagged(by_predictor, "out_of_sample"),
        "decay": Tagged(decay_frame, "out_of_sample"),
        "composites_later": Tagged(later, "out_of_sample"),
        "composite_in_sample": Tagged(composite.loc[["in_sample"]], "in_sample"),
    }
    return ExperimentOutput(tables=tables, scalars=scalars, report_html=render_html(report))


KIND = ExperimentKind(
    name="study_factor_zoo",
    description="Study 3: the factor zoo, multiple testing and post-publication decay",
    inputs=tuple(INPUTS),
    needs_seed=False,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
)
