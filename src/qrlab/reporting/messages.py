"""Italian forms of the library's messages shown in a report (design 8.7).

The library writes its messages in English: import notes, the reasons a health check does not
apply, metric errors and measurement details. A report in Italian translates them here.

Each entry matches one whole English message with a regular expression; the captured values
(names, counts, numbers) are carried over, decimals with the Italian comma. Only whole
messages are translated, never fragments, so text written by the user is never touched. A
message with no entry is shown as it is: ``tests/unit/reporting/test_messages.py`` scans the
library's source and fails if a message template has no entry here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType

from qrlab.reporting.formatting import Language

__all__ = ["CATALOG", "DETAIL_KEYS", "detail_key", "detail_value", "is_known", "translate"]

_DIMENSIONS = {
    "country": "paese",
    "sector": "settore",
    "currency": "valuta",
    "underlying_currency": "valuta sottostante",
    "security": "titolo",
    "issuer": "emittente",
}
_DIRECTIONS = {"up": "positivi", "down": "negativi"}

# (English pattern, Italian template, word maps for some groups by position)
_ENTRIES: tuple[tuple[str, str, Mapping[int, Mapping[str, str]]], ...] = (
    # --- why a health check does not apply ------------------------------------------
    (r"no positions held", "nessuna posizione detenuta", {}),
    (r"no TER known for any position", "nessun TER noto per le posizioni", {}),
    (r"the period has zero length", "il periodo ha durata nulla", {}),
    (
        r"needs both a known TER and a non-zero period",
        "servono un TER noto e un periodo non nullo",
        {},
    ),
    (r"no target weights given", "nessun peso obiettivo indicato", {}),
    (
        r"the converter does not record carried-forward rates",
        "il convertitore non registra i cambi presi da date precedenti",
        {},
    ),
    (r"needs at least two positions", "servono almeno due posizioni", {}),
    (r"no price series for (.+)", "nessuna serie di prezzi per {0}", {}),
    (
        r"(\d+) common returns, fewer than the window of (\d+)",
        "{0} rendimenti comuni, meno della finestra di {1}",
        {},
    ),
    (
        r"a position has zero return variance over the window",
        "una posizione ha varianza dei rendimenti nulla nella finestra",
        {},
    ),
    (r"no funds with master data held", "nessun fondo con anagrafica in portafoglio", {}),
    (r"no fund size known", "dimensione dei fondi non nota", {}),
    (r"no inception date known", "data di lancio dei fondi non nota", {}),
    (r"no look-through inputs given", "nessun dato di look-through fornito", {}),
    (
        r"no (\w+) known through holdings",
        "{0}: nessun valore noto dalle holdings",
        {0: _DIMENSIONS},
    ),
    (r"needs holdings of at least two funds", "servono le holdings di almeno due fondi", {}),
    (
        r"no held fund has a year of tracking data",
        "nessun fondo detenuto ha un anno di dati di tracking",
        {},
    ),
    (
        r"no held fund has enough tracking data",
        "nessun fondo detenuto ha abbastanza dati di tracking",
        {},
    ),
    (r"no tracked fund has a known TER", "nessun fondo con tracking ha un TER noto", {}),
    (
        r"no portfolio return series given",
        "nessuna serie di rendimenti del portafoglio fornita",
        {},
    ),
    (r"no benchmark given", "nessun benchmark indicato", {}),
    # --- metric errors ------------------------------------------------------------------
    (
        r"tracking difference needs at least two dates",
        "la tracking difference richiede almeno due date",
        {},
    ),
    (
        r"(\S+): needs at least (\d+) observation\(s\), got (\d+)",
        "{0}: servono almeno {1} osservazioni, presenti {2}",
        {},
    ),
    (r"(\S+): zero variance", "{0}: varianza nulla", {}),
    (r"calmar_ratio: no drawdown in the sample", "calmar_ratio: nessun drawdown nel campione", {}),
    (
        r"final wealth (\S+) <= 0: no compound growth rate",
        "ricchezza finale {0} <= 0: nessun tasso di crescita composto",
        {},
    ),
    (
        r"sortino_ratio: no return below the target",
        "sortino_ratio: nessun rendimento sotto l'obiettivo",
        {},
    ),
    (
        r"gain_loss_ratio needs at least one gain and one loss",
        "gain_loss_ratio richiede almeno un guadagno e una perdita",
        {},
    ),
    (
        r"Mertens variance is not positive for these moments",
        "la varianza di Mertens non è positiva per questi momenti",
        {},
    ),
    (
        r"information_ratio: tracking error is zero",
        "information_ratio: il tracking error è nullo",
        {},
    ),
    (
        r"capm_regression: benchmark has zero variance",
        "capm_regression: il benchmark ha varianza nulla",
        {},
    ),
    (
        r"capm_regression: R-squared undefined \(portfolio is constant\)",
        "capm_regression: R² non definito (portafoglio costante)",
        {},
    ),
    (
        r"(\w+)_capture: the benchmark has no (\w+) periods",
        "{0}_capture: il benchmark non ha periodi {1}",
        {1: _DIRECTIONS},
    ),
    (
        r"(\w+)_capture: final wealth <= 0 over the selected periods",
        "{0}_capture: ricchezza finale <= 0 nei periodi selezionati",
        {},
    ),
    (
        r"(\d+) observations leave a tail of (\S+) at confidence (\S+); need >= 1",
        "{0} osservazioni lasciano una coda di {1} al livello di confidenza {2}; ne serve almeno 1",
        {},
    ),
    (r"PSR needs at least 3 observations", "il PSR richiede almeno 3 osservazioni", {}),
    (
        r"PSR is undefined for these moments \(skewness (\S+), kurtosis (\S+)\)",
        "il PSR non è definito per questi momenti (asimmetria {0}, curtosi {1})",
        {},
    ),
    (
        r"the difference of the Sharpe ratios has zero variance",
        "la differenza degli Sharpe ratio ha varianza nulla",
        {},
    ),
    (r"a series has zero variance", "una serie ha varianza nulla", {}),
    (
        r"a Sharpe-ratio test needs at least 3 observations",
        "un test sullo Sharpe ratio richiede almeno 3 osservazioni",
        {},
    ),
    (
        r"xirr needs at least one negative and one positive flow",
        "l'XIRR richiede almeno un flusso negativo e uno positivo",
        {},
    ),
    (
        r"xirr: no rate between -99\.9999 % and 1e8 % solves the flows",
        "XIRR: nessun tasso tra -99,9999 % e 1e8 % risolve i flussi",
        {},
    ),
    (
        r"portfolio volatility is zero: contributions are undefined",
        "la volatilità del portafoglio è nulla: i contributi non sono definiti",
        {},
    ),
    (
        r"portfolio variance is zero: effective bets are undefined",
        "la varianza del portafoglio è nulla: le scommesse effettive non sono definite",
        {},
    ),
    (
        r"warm-up returns have zero variance: cannot filter",
        "i rendimenti iniziali hanno varianza nulla: impossibile filtrare",
        {},
    ),
    (
        r"Cornish-Fisher expansion is not a quantile on the tail "
        r"\(skewness (\S+), excess kurtosis (\S+)\)",
        "l'espansione di Cornish-Fisher non è un quantile nella coda "
        "(asimmetria {0}, curtosi in eccesso {1})",
        {},
    ),
    # --- import notes -------------------------------------------------------------------
    (
        r"File listed newest first; rows reversed as a whole \(chronological order\)\.",
        "File ordinato dalla riga più recente; righe invertite in blocco (ordine cronologico).",
        {},
    ),
    (
        r"Amounts were signed in the file; signs checked against each kind and removed\.",
        "Importi con segno nel file; segni verificati rispetto a ogni tipo di operazione e "
        "rimossi.",
        {},
    ),
    (
        r"Empty fees and taxes recorded as zero (\S+)\.",
        "Commissioni e imposte vuote registrate come zero {0}.",
        {},
    ),
    (r"Ignored columns: (.+)\.", "Colonne ignorate: {0}.", {}),
    (
        r"Rows reversed from the file's newest-first order\.",
        "Righe invertite rispetto all'ordine del file, dalla più recente.",
        {},
    ),
    (
        r"Empty cells kept as NaN; no forward fill\.",
        "Celle vuote lasciate come mancanti; nessun riempimento con valori precedenti.",
        {},
    ),
    (
        r"Skipped (\d+) preamble line\(s\) before the header\.",
        "Saltate {0} righe di preambolo prima dell'intestazione.",
        {},
    ),
    (r"Cells equal to (.+) treated as unknown\.", "Celle uguali a {0} trattate come ignote.", {}),
    (
        r"Weights converted from percent to decimal \(divided by 100\)\.",
        "Pesi convertiti da percentuale a decimale (divisi per 100).",
        {},
    ),
    (
        r"Country names converted to ISO 3166-1 alpha-2 codes\.",
        "Nomi dei paesi convertiti in codici ISO 3166-1 alpha-2.",
        {},
    ),
    (
        r"Ignored (\d+) line\(s\) after the first blank line\.",
        "Ignorate {0} righe dopo la prima riga vuota.",
        {},
    ),
    (r"Read sheet (.+) of an xlsx workbook\.", "Letto il foglio {0} di una cartella xlsx.", {}),
    (r"Symbols removed from numbers: (.+)\.", "Simboli rimossi dai numeri: {0}.", {}),
    # --- fixed phrases in measurement details ------------------------------------------
    (
        r"security, not issuer \(no issuer map\)",
        "titolo, non emittente (nessuna mappa degli emittenti)",
        {},
    ),
)

CATALOG: tuple[tuple[re.Pattern[str], str, Mapping[int, Mapping[str, str]]], ...] = tuple(
    (re.compile(pattern), template, maps) for pattern, template, maps in _ENTRIES
)
"""Compiled entries, matched in order against a whole message."""

DETAIL_KEYS: Mapping[str, str] = MappingProxyType(
    {
        "isin": "ISIN",
        "positions": "posizioni",
        "effective_positions": "posizioni effettive",
        "excluded_weight": "peso escluso",
        "ter": "TER",
        "drag": "costi di negoziazione",
        "holding": "posizione",
        "deviation": "scostamento",
        "instruments": "strumenti",
        "currencies": "valute",
        "missing": "mancanti",
        "residual": "residuo",
        "pairs": "coppie",
        "window": "finestra",
        "securities": "titoli",
        "period": "periodo",
        "funds": "fondi",
        "unknown_weight": "peso non noto",
        "unmatched": "senza ISIN",
        "r_squared": "R²",
        "grouping": "raggruppamento",
        "unknown": "non noto",
        "unexplained": "non spiegato",
        "not looked through": "non analizzato",
        **_DIMENSIONS,
    }
)
"""Italian names of the keys of measurement details."""

_DECIMAL = re.compile(r"^-?\d+\.\d+$")
_NUMBERS = re.compile(r"^[+-]?\d+(\.\d+)?( / [+-]?\d+(\.\d+)?)*$")
_DETAIL_WORDS = {"cash": "liquidità"}


def _match(text: str) -> tuple[re.Match[str], str, Mapping[int, Mapping[str, str]]] | None:
    for pattern, template, maps in CATALOG:
        found = pattern.fullmatch(text)
        if found is not None:
            return found, template, maps
    return None


def is_known(text: str) -> bool:
    """Return whether ``text`` is a library message with an Italian form."""
    return _match(text) is not None


def translate(text: str, language: Language) -> str:
    """Return ``text`` in ``language``: unchanged in English or when it is not in the catalog."""
    if language is not Language.IT:
        return text
    found = _match(text)
    if found is None:
        return text
    match, template, maps = found
    values = []
    for i, group in enumerate(match.groups()):
        if i in maps:
            values.append(maps[i].get(group, group))
        elif _DECIMAL.match(group):
            values.append(group.replace(".", ","))
        else:
            values.append(group)
    return template.format(*values)


def detail_key(key: str, language: Language) -> str:
    """Return the name of a measurement-detail key in ``language``."""
    return DETAIL_KEYS.get(key, key) if language is Language.IT else key


def detail_value(text: str, language: Language) -> str:
    """Return a measurement-detail value in ``language``.

    Values made only of numbers (``"0.001744"``, ``"+0.4256"``, ``"0.1 / 0.2"``) get the
    Italian decimal comma; the word ``"cash"`` becomes ``"liquidità"``; anything else goes
    through :func:`translate`.
    """
    if language is not Language.IT:
        return text
    if _NUMBERS.match(text):
        return re.sub(r"(?<=\d)\.(?=\d)", ",", text)
    return _DETAIL_WORDS.get(text, translate(text, language))
