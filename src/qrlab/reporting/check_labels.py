"""Names and plain-language explanations of the health checks, in Italian and English.

Keyed by check id. Both languages must cover exactly the registered checks (tested), so a new
check cannot reach a report without an explanation.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from qrlab.reporting.formatting import Language

__all__ = ["CHECK_LABELS", "check_label"]

_EN: dict[str, tuple[str, str]] = {
    "concentration.largest_position": (
        "Largest position",
        "Weight of the largest single position. A high value ties the result to one holding.",
    ),
    "concentration.top5": (
        "Five largest positions",
        "Combined weight of the five largest positions.",
    ),
    "concentration.herfindahl": (
        "Concentration index (HHI)",
        "Sum of squared weights; its inverse is the effective number of positions.",
    ),
    "concentration.foreign_currency": (
        "Largest foreign currency",
        "Weight exposed to the largest single non-base currency, after share-class hedging.",
    ),
    "diversification.average_correlation": (
        "Average correlation",
        "Mean pairwise correlation of position returns. High values mean the positions "
        "tend to move together.",
    ),
    "diversification.ratio": (
        "Diversification ratio",
        "Weighted average volatility over portfolio volatility. A value near 1 means "
        "little risk is diversified away.",
    ),
    "risk.volatility": (
        "Volatility",
        "Annualised standard deviation of portfolio returns.",
    ),
    "risk.max_drawdown": (
        "Maximum drawdown",
        "Largest fall from a previous peak of the return path.",
    ),
    "risk.expected_shortfall": (
        "Expected shortfall",
        "Average loss in the worst periods beyond the confidence level (historical).",
    ),
    "risk.beta": (
        "Beta",
        "Sensitivity of portfolio returns to benchmark returns (OLS).",
    ),
    "risk.skewness": (
        "Skewness",
        "Asymmetry of returns. Negative values mean large losses are more frequent than "
        "large gains.",
    ),
    "costs.weighted_ter": (
        "Weighted TER",
        "Ongoing fund charges, weighted by position (funds with unknown TER excluded).",
    ),
    "costs.trading_drag": (
        "Trading costs",
        "Commissions and charges paid on trades, a year, over the average portfolio value.",
    ),
    "costs.total_cost": (
        "Total cost",
        "Weighted TER plus trading costs, a year.",
    ),
    "etf_quality.synthetic_share": (
        "Synthetic replication",
        "Weight in funds replicating their index with swaps (counterparty exposure).",
    ),
    "etf_quality.domicile": (
        "Fund domicile",
        "Weight in funds domiciled outside the preferred countries.",
    ),
    "etf_quality.distribution": (
        "Distribution policy",
        "Weight in funds whose distribution policy differs from the preferred one.",
    ),
    "etf_quality.fund_size": (
        "Fund size",
        "Fund assets in base currency. Small funds are more likely to be closed or merged.",
    ),
    "etf_quality.fund_age": (
        "Fund age",
        "Years since the fund was launched: a short history gives little evidence.",
    ),
    "currency.unhedged_foreign": (
        "Unhedged foreign currency",
        "Total weight exposed to currencies other than the base currency, cash included.",
    ),
    "drift.max_deviation": (
        "Largest drift",
        "Largest difference between a current weight and its target.",
    ),
    "drift.total": (
        "Total drift",
        "Half the sum of the differences from the targets: the share to trade to rebalance.",
    ),
    "data_quality.stale_prices": (
        "Carried-forward prices",
        "Prices taken from an earlier date than the report date.",
    ),
    "data_quality.stale_fx": (
        "Carried-forward FX rates",
        "Exchange rates taken from an earlier date than requested.",
    ),
    "data_quality.stale_master": (
        "Old master data",
        "Instrument records older than the configured age.",
    ),
    "data_quality.missing_master": (
        "Missing master data",
        "Held instruments without a record, or with required fields unknown.",
    ),
    "data_quality.pnl_residual": (
        "Profit and loss residual",
        "Part of the profit and loss not explained by its components: should be zero.",
    ),
}

_IT: dict[str, tuple[str, str]] = {
    "concentration.largest_position": (
        "Posizione più grande",
        "Peso della singola posizione più grande. Un valore alto lega il risultato a un titolo.",
    ),
    "concentration.top5": (
        "Prime cinque posizioni",
        "Peso complessivo delle cinque posizioni più grandi.",
    ),
    "concentration.herfindahl": (
        "Indice di concentrazione (HHI)",
        "Somma dei pesi al quadrato; il suo inverso è il numero effettivo di posizioni.",
    ),
    "concentration.foreign_currency": (
        "Valuta estera principale",
        "Peso esposto alla principale valuta diversa da quella di base, al netto delle "
        "classi coperte.",
    ),
    "diversification.average_correlation": (
        "Correlazione media",
        "Media delle correlazioni a coppie dei rendimenti delle posizioni. Valori alti "
        "indicano che le posizioni tendono a muoversi insieme.",
    ),
    "diversification.ratio": (
        "Rapporto di diversificazione",
        "Volatilità media ponderata diviso volatilità del portafoglio. Un valore vicino a 1 "
        "indica poco rischio diversificato.",
    ),
    "risk.volatility": (
        "Volatilità",
        "Deviazione standard annualizzata dei rendimenti del portafoglio.",
    ),
    "risk.max_drawdown": (
        "Drawdown massimo",
        "Massima perdita da un picco precedente del percorso dei rendimenti.",
    ),
    "risk.expected_shortfall": (
        "Expected shortfall",
        "Perdita media nei periodi peggiori oltre il livello di confidenza (storica).",
    ),
    "risk.beta": (
        "Beta",
        "Sensibilità dei rendimenti del portafoglio a quelli del benchmark (OLS).",
    ),
    "risk.skewness": (
        "Asimmetria",
        "Asimmetria dei rendimenti. Valori negativi indicano perdite forti più frequenti "
        "dei guadagni forti.",
    ),
    "costs.weighted_ter": (
        "TER ponderato",
        "Costi correnti dei fondi, ponderati per posizione (esclusi i fondi con TER ignoto).",
    ),
    "costs.trading_drag": (
        "Costi di negoziazione",
        "Commissioni e oneri pagati sulle operazioni, annui, sul valore medio del portafoglio.",
    ),
    "costs.total_cost": (
        "Costo totale",
        "TER ponderato più costi di negoziazione, annui.",
    ),
    "etf_quality.synthetic_share": (
        "Replica sintetica",
        "Peso dei fondi che replicano l'indice con swap (esposizione alla controparte).",
    ),
    "etf_quality.domicile": (
        "Domicilio dei fondi",
        "Peso dei fondi domiciliati fuori dai paesi preferiti.",
    ),
    "etf_quality.distribution": (
        "Politica di distribuzione",
        "Peso dei fondi con politica di distribuzione diversa da quella preferita.",
    ),
    "etf_quality.fund_size": (
        "Dimensione del fondo",
        "Patrimonio del fondo in valuta di base. I fondi piccoli rischiano di più la chiusura "
        "o la fusione.",
    ),
    "etf_quality.fund_age": (
        "Età del fondo",
        "Anni dal lancio del fondo: una storia breve offre poca evidenza.",
    ),
    "currency.unhedged_foreign": (
        "Valuta estera non coperta",
        "Peso totale esposto a valute diverse da quella di base, liquidità inclusa.",
    ),
    "drift.max_deviation": (
        "Scostamento massimo",
        "Massima differenza tra un peso attuale e il suo obiettivo.",
    ),
    "drift.total": (
        "Scostamento totale",
        "Metà della somma degli scostamenti dagli obiettivi: la quota da negoziare per "
        "ribilanciare.",
    ),
    "data_quality.stale_prices": (
        "Prezzi riportati",
        "Prezzi presi da una data precedente a quella del report.",
    ),
    "data_quality.stale_fx": (
        "Cambi riportati",
        "Tassi di cambio presi da una data precedente a quella richiesta.",
    ),
    "data_quality.stale_master": (
        "Anagrafiche vecchie",
        "Anagrafiche degli strumenti più vecchie dell'età configurata.",
    ),
    "data_quality.missing_master": (
        "Anagrafiche mancanti",
        "Strumenti in portafoglio senza anagrafica, o con campi obbligatori ignoti.",
    ),
    "data_quality.pnl_residual": (
        "Residuo del risultato",
        "Parte del risultato non spiegata dalle sue componenti: deve essere zero.",
    ),
}

CHECK_LABELS: Mapping[Language, Mapping[str, tuple[str, str]]] = MappingProxyType(
    {Language.EN: MappingProxyType(_EN), Language.IT: MappingProxyType(_IT)}
)
"""``(name, explanation)`` per check id and language."""


def check_label(check_id: str, language: Language) -> tuple[str, str]:
    """Return ``(name, explanation)`` of the check ``check_id`` in ``language``."""
    return CHECK_LABELS[language][check_id]
