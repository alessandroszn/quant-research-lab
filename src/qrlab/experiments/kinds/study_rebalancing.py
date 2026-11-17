"""Experiment kind ``study_rebalancing``: study 4, rebalancing rules for a EUR ETF investor.

Inputs: ``kf_developed`` (Ken French ``Developed_3_Factors`` zip), ``ecb_fx``
(``eurofxref-hist.zip``) and ``yc_6y`` / ``yc_7y`` (ECB AAA spot rates, Data Portal CSV). The
equity asset is the Developed market (Mkt-RF + RF) converted to EUR; the bond asset is a rolled
7-year AAA zero-coupon bond. All results are tagged ``descriptive``: fixed rules on one history
and on resampled paths of it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.data.ecb import FX_DATASET, parse_ecb_fx, parse_yield_curve
from qrlab.data.ecb import SOURCE as ECB_SOURCE
from qrlab.data.ecb import TERMS as ECB_TERMS
from qrlab.data.ken_french import parse_ken_french
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds import _fields as s
from qrlab.experiments.kinds._params import day, number, table, text, whole
from qrlab.experiments.kinds._studies import describe, ken_french_provenance, names, raw_provenance
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.experiments.runner import configurations_tried
from qrlab.experiments.schema import FieldKind, KindSchema
from qrlab.optimization.rebalancing import CostModel
from qrlab.reporting.html import render_html
from qrlab.studies.rebalancing import (
    POLICIES,
    compare_to_reference,
    equity_returns_eur,
    historical_runs,
    hypotheses,
    month_end_observations,
    simulate,
    summarize_runs,
    zero_coupon_returns,
)
from qrlab.studies.rebalancing_report import build_rebalancing_report

__all__ = ["INPUTS", "KIND", "SCHEMA"]

INPUTS: Mapping[str, str] = {
    "kf_developed": "Developed_3_Factors",
    "ecb_fx": FX_DATASET,
    "yc_6y": "yc_aaa_spot_6y",
    "yc_7y": "yc_aaa_spot_7y",
}
"""Input name -> dataset."""

BOND_MATURITY = 7.0  # years (design note)

_PARAMETERS = (
    "equity_weight",
    "policies",
    "reference",
    "cost_scenarios",
    "tax_rate",
    "initial_value",
    "end",
    "horizon_months",
    "n_paths",
    "mean_block_length",
    "support_share",
)

_POLICY_HELP = (
    "A rebalancing rule: buy_and_hold, calendar_* (monthly, quarterly, annual) or band_* "
    "(5 or 10 points, back to the target or to the band's edge).",
    "Una regola di ribilanciamento: buy_and_hold, calendar_* (mensile, trimestrale, annuale) o "
    "band_* (5 o 10 punti, fino al peso obiettivo o al bordo della banda).",
)

SCHEMA = KindSchema(
    inputs=(
        s.file(
            "kf_developed",
            "Ken French Developed-markets three-factor file, monthly, the zip file as downloaded.",
            "Ken French file dei tre fattori dei mercati sviluppati, mensile, il file zip così "
            "come scaricato.",
        ),
        s.file(
            "ecb_fx",
            "ECB euro reference exchange rates, full history (eurofxref-hist.zip), as downloaded.",
            "Tassi di cambio di riferimento dell'euro della BCE, storico completo "
            "(eurofxref-hist.zip), così come scaricato.",
        ),
        s.file(
            "yc_6y",
            "ECB AAA euro-area yield curve, 6-year spot rate (Data Portal CSV), as downloaded.",
            "Curva dei rendimenti AAA dell'area euro della BCE, tasso spot a 6 anni (CSV del "
            "Data Portal), così come scaricato.",
        ),
        s.file(
            "yc_7y",
            "ECB AAA euro-area yield curve, 7-year spot rate (Data Portal CSV), as downloaded.",
            "Curva dei rendimenti AAA dell'area euro della BCE, tasso spot a 7 anni (CSV del "
            "Data Portal), così come scaricato.",
        ),
    ),
    parameters=(
        s.number(
            "equity_weight",
            "Target weight of equities, strictly between 0 and 1; bonds hold the rest.",
            "Peso obiettivo delle azioni, strettamente tra 0 e 1; le obbligazioni hanno il resto.",
            minimum=0.0,
            maximum=1.0,
            open_minimum=True,
            open_maximum=True,
            unit="fraction",
        ),
        s.listing(
            "policies",
            "Rebalancing rules to compare, without repeats.",
            "Regole di ribilanciamento da confrontare, senza ripetizioni.",
            s.choice("policy", *_POLICY_HELP, tuple(POLICIES)),
        ),
        s.choice(
            "reference",
            "The policy the others are compared with; it must be one of policies.",
            "La regola con cui si confrontano le altre; deve essere tra le policies.",
            tuple(POLICIES),
        ),
        s.mapping(
            "cost_scenarios",
            "Cost scenarios by name, each with a proportional and a fixed cost.",
            "Scenari di costo per nome, ognuno con un costo proporzionale e uno fisso.",
            FieldKind.TEXT,
            s.table(
                "scenario",
                "The costs of one scenario.",
                "I costi di uno scenario.",
                (
                    s.number(
                        "proportional",
                        "Cost per unit of the amount traded, at least 0.",
                        "Costo per unità dell'importo scambiato, non negativo.",
                        minimum=0.0,
                        unit="fraction",
                    ),
                    s.number(
                        "fixed",
                        "Fixed fee in EUR per asset traded, at least 0.",
                        "Commissione fissa in EUR per ogni attività scambiata, non negativa.",
                        minimum=0.0,
                        unit="currency units",
                    ),
                ),
            ),
        ),
        s.number(
            "tax_rate",
            "Tax rate on realised gains, from 0 up to but excluding 1.",
            "Aliquota sulle plusvalenze realizzate, da 0 incluso a 1 escluso.",
            minimum=0.0,
            maximum=1.0,
            open_maximum=True,
            unit="fraction",
        ),
        s.number(
            "initial_value",
            "Starting value of the portfolio in EUR, positive.",
            "Valore iniziale del portafoglio in EUR, positivo.",
            minimum=0.0,
            open_minimum=True,
            unit="currency units",
        ),
        s.day(
            "end",
            "Last day of the history; returns after its month are not used.",
            "Ultimo giorno della storia; i rendimenti dopo il suo mese non sono usati.",
        ),
        s.integer(
            "horizon_months",
            "Length of each resampled path.",
            "Lunghezza di ogni percorso ricampionato.",
            minimum=12,
            unit="months",
        ),
        s.integer(
            "n_paths",
            "Number of resampled paths.",
            "Numero di percorsi ricampionati.",
            minimum=1,
        ),
        s.number(
            "mean_block_length",
            "Average block length of the stationary bootstrap that resamples the history.",
            "Lunghezza media dei blocchi del bootstrap stazionario che ricampiona la storia.",
            unit="months",
        ),
        s.number(
            "support_share",
            "Share of paths on which a hypothesis must hold to be supported, above 0.5 up to 1.",
            "Quota di percorsi su cui un'ipotesi deve valere per essere confermata, oltre 0,5 e "
            "fino a 1.",
            minimum=0.5,
            maximum=1.0,
            open_minimum=True,
            unit="fraction",
        ),
    ),
)


@dataclass(frozen=True)
class _Parameters:
    equity_weight: float
    policies: tuple[str, ...]
    reference: str
    costs: Mapping[str, CostModel]
    tax_rate: float
    initial_value: float
    end: date
    horizon: int
    n_paths: int
    mean_block_length: float
    support_share: float


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    weight = number(parameters, "equity_weight")
    if not 0.0 < weight < 1.0:
        raise ValidationError("equity_weight must be strictly between 0 and 1")
    policies = names(parameters, "policies")
    unknown = sorted(set(policies) - set(POLICIES))
    if unknown:
        raise ValidationError(f"unknown policies {unknown}; known: {list(POLICIES)}")
    reference = text(parameters, "reference")
    if reference not in policies:
        raise ValidationError("reference must be one of the policies")
    scenarios = parameters["cost_scenarios"]
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValidationError("cost_scenarios must be a non-empty table of {proportional, fixed}")
    costs = {}
    for name in scenarios:
        spec = table(scenarios, name, required={"proportional", "fixed"}, optional=set())
        costs[str(name)] = CostModel(number(spec, "proportional"), number(spec, "fixed"))
    tax = number(parameters, "tax_rate")
    if not 0.0 <= tax < 1.0:
        raise ValidationError("tax_rate must be in [0, 1)")
    initial = number(parameters, "initial_value")
    if not initial > 0:
        raise ValidationError("initial_value must be positive")
    share = number(parameters, "support_share")
    if not 0.5 < share <= 1.0:
        raise ValidationError("support_share must be in (0.5, 1]")
    return _Parameters(
        equity_weight=weight,
        policies=policies,
        reference=reference,
        costs=costs,
        tax_rate=tax,
        initial_value=initial,
        end=day(parameters, "end"),
        horizon=whole(parameters, "horizon_months", minimum=12),
        n_paths=whole(parameters, "n_paths", minimum=1),
        mean_block_length=number(parameters, "mean_block_length"),
        support_share=share,
    )


def _returns(context: RunContext, end: date) -> tuple[pd.DataFrame, list[str]]:
    facts = []

    def read(name: str) -> tuple[bytes, object]:
        path = context.inputs[name]
        if name == "kf_developed":
            provenance = ken_french_provenance(path, INPUTS[name])
        else:
            provenance = raw_provenance(
                path, source=ECB_SOURCE, dataset=INPUTS[name], terms=ECB_TERMS
            )
        facts.append(describe(provenance))
        return path.read_bytes(), provenance

    kf = parse_ken_french(*read("kf_developed"), frequency=Frequency.MONTHLY).data  # type: ignore[arg-type]
    usd = (kf["Mkt-RF"] + kf["RF"]).dropna()
    fx = parse_ecb_fx(*read("ecb_fx")).data[["USD"]]  # type: ignore[arg-type]
    rates = month_end_observations(fx)["USD"]
    six = parse_yield_curve(*read("yc_6y")).data  # type: ignore[arg-type]
    seven = parse_yield_curve(*read("yc_7y")).data  # type: ignore[arg-type]
    curve = six.join(seven, how="inner")
    bond = zero_coupon_returns(
        month_end_observations(curve), short="SR_6Y", long="SR_7Y", maturity=BOND_MATURITY
    )
    equity = equity_returns_eur(usd, rates)
    returns = pd.concat({"equity": equity, "bond": bond}, axis=1, join="inner")
    returns = returns.loc[returns.index <= pd.Timestamp(end) + pd.offsets.MonthEnd(0)]
    if returns.empty:
        raise ValidationError("no month has both equity and bond returns")
    expected = pd.date_range(returns.index[0], returns.index[-1], freq="ME")
    if len(expected) != len(returns):
        raise ValidationError("equity and bond returns must cover consecutive months")
    return returns, facts


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    returns, facts = _returns(context, p.end)
    weights = pd.Series({"equity": p.equity_weight, "bond": 1.0 - p.equity_weight})
    common = {
        "weights": weights,
        "equity": "equity",
        "policies": p.policies,
        "cost_scenarios": p.costs,
        "tax_rate": p.tax_rate,
        "initial_value": p.initial_value,
    }
    history = historical_runs(returns, **common)  # type: ignore[arg-type]
    runs = simulate(
        returns,
        horizon=p.horizon,
        n_paths=p.n_paths,
        mean_block_length=p.mean_block_length,
        rng=np.random.default_rng(int(context.seed)),  # type: ignore[arg-type]
        **common,  # type: ignore[arg-type]
    )
    summary = summarize_runs(runs)
    comparison = compare_to_reference(runs, reference=p.reference)
    verdicts = hypotheses(runs, support_share=p.support_share)
    annual = returns.mean() * 12
    vol = returns.std(ddof=1) * np.sqrt(12)
    config = context.config
    tried = configurations_tried(config.output_dir.parent, config.name, including=config.hash)
    report = build_rebalancing_report(
        title=f"Study 4: rebalancing for a EUR ETF investor ({config.name})",
        hypothesis=config.hypothesis,
        facts=[
            (
                "Sample",
                f"{returns.index[0].date()} to {returns.index[-1].date()} ({len(returns)} months)",
            ),
            (
                "Assets (EUR, monthly)",
                f"equity mean {annual['equity']:.2%} p.a., volatility {vol['equity']:.2%}; "
                f"bond mean {annual['bond']:.2%} p.a., volatility {vol['bond']:.2%}; "
                f"correlation {returns['equity'].corr(returns['bond']):.2f}",
            ),
            (
                "Specification",
                f"target equity {p.equity_weight:.0%}; initial EUR {p.initial_value:,.0f}; tax "
                f"{p.tax_rate:.0%} on realised gains, no loss offset, liquidation at the end; "
                f"{p.n_paths} paths of {p.horizon} months, mean block {p.mean_block_length:g}; "
                f"reference {p.reference}; support share {p.support_share:.2f}",
            ),
            (
                "Cost scenarios",
                "; ".join(
                    f"{k}: {c.proportional:.2%} + EUR {c.fixed:g} per trade"
                    for k, c in p.costs.items()
                ),
            ),
            ("Configurations tried", str(tried)),
            *(("Data", line) for line in facts),
        ],
        historical=history,
        simulated=summary,
        comparison=comparison,
        verdicts=verdicts,
    )
    scalars: dict[str, Tagged] = {
        "configurations_tried": Tagged(float(tried), "descriptive"),
        "months": Tagged(float(len(returns)), "descriptive"),
    }
    for row in verdicts.drop_duplicates(["scenario", "hypothesis"]).itertuples():
        key = f"{row.hypothesis}_{row.scenario}_supported"
        scalars[key] = Tagged(float(bool(row.supported)), "descriptive")
    return ExperimentOutput(
        tables={
            "asset_returns": Tagged(returns, "descriptive"),
            "historical": Tagged(history, "descriptive"),
            "simulated_summary": Tagged(summary, "descriptive"),
            "simulated_runs": Tagged(runs, "descriptive"),
            "against_reference": Tagged(comparison, "descriptive"),
            "hypotheses": Tagged(verdicts, "descriptive"),
        },
        scalars=scalars,
        report_html=render_html(report),
    )


KIND = ExperimentKind(
    name="study_rebalancing",
    description="Study 4: rebalancing rules for a EUR ETF investor after costs, tax and FX",
    inputs=tuple(INPUTS),
    needs_seed=True,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
    schema=SCHEMA,
)
