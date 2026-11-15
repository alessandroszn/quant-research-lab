"""Every user-visible string of the app, in English and Italian.

Identifiers that must match files on disk and the command line (kind names, file names, table,
column and scalar names) and the runner's own messages are never translated.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

__all__ = ["LANGUAGES", "STRINGS", "tr", "tr_value"]

LANGUAGES = ("en", "it")

_EN = {
    "app.title": "Quant Research Lab",
    "app.title_workspace": "Quant Research Lab — {name}",
    "app.disclaimer": (
        "Research analytics, not investment advice. Every number comes from the qrlab library "
        "through the same runner as the command line."
    ),
    "language.en": "English",
    "language.it": "Italiano",
    "nav.home": "Home",
    "nav.portfolios": "Portfolios",
    "nav.portfolio": "Portfolio report",
    "nav.risk": "Risk",
    "nav.scenarios": "Scenarios",
    "nav.projections": "Projections",
    "nav.optimiser": "Optimiser",
    "nav.backtests": "Backtests & studies",
    "nav.data": "Data",
    "nav.history": "History",
    "nav.settings": "Settings",
    "home.open": "Open workspace…",
    "home.create": "Create workspace…",
    "home.none": "No workspace open.",
    "home.current": "Workspace: {path}",
    "home.recent": "Recent workspaces",
    "home.missing": "{path} (not found)",
    "screen.configs": "Configs",
    "screen.new": "New from template",
    "screen.duplicate": "Duplicate",
    "screen.refresh": "Refresh",
    "screen.save": "Save",
    "screen.validate": "Validate",
    "screen.run": "Run",
    "screen.open_report": "Open report",
    "screen.open_folder": "Open folder",
    "screen.no_workspace": "Open a workspace first (Home).",
    "screen.new_name": "File name for the new config (without .toml):",
    "screen.kind": "Kind of the new config:",
    "screen.overwrite": "{name} already has outputs from an earlier run. Replace them?",
    "screen.unsaved": "{name} has unsaved changes. Save them?",
    "screen.running": "Running… {seconds} s",
    "screen.done": "Finished: {status}.",
    "screen.failed": "Failed: {error}",
    "screen.valid": "Valid: {name} ({kind}).",
    "screen.invalid": "Not valid: {error}",
    "screen.busy": "Another run is in progress.",
    "results.scalars": "Scalars",
    "results.figures": "Figures",
    "results.scalar_columns": "Name|Value|Sample",
    "data.columns": "Source|Dataset|Retrieved|Age (days)|Latest|Bytes|SHA-256|Terms",
    "data.latest": "yes",
    "history.columns": "Finished|Name|Kind|Status|Configurations|Folder|Error",
    "history.open": "Open folder",
    "settings.language": "Language",
    "settings.recent": "Recent workspaces",
    "settings.remove": "Remove",
    "settings.clear": "Clear",
    "settings.about": "About",
    "settings.version": "Quant Research Lab {version} — Python {python}, Qt {qt}",
    "settings.file": "Settings are saved in {path}.",
    "settings.busy": "The language cannot change while a run is in progress.",
    "close.busy": (
        "A run is in progress and cannot be stopped. Wait for it to finish, then close the app."
    ),
    "tag.in_sample": "in-sample",
    "tag.out_of_sample": "out-of-sample",
    "tag.descriptive": "descriptive",
    "status.success": "success",
    "status.failure": "failure",
    "error.no_record": "No record.json in {folder}: the run did not finish.",
    "error.not_folder": "{folder} is not a folder.",
    "error.workspace": "Cannot use {folder} as a workspace: {message}",
    "error.unknown_kinds": "Unknown kinds: {kinds}.",
    "error.not_on_screen": "{kind} is not shown on this screen.",
    "error.no_selection": "No config is selected.",
    "error.bad_name": "{name} is not a valid file name.",
    "error.exists": "{name} already exists.",
    "error.language": "Unsupported language: {code}.",
    "error.import": "Cannot import {name}: {message}",
    "portfolio.list": "Portfolios",
    "portfolio.new": "New portfolio",
    "portfolio.new_name": "Name of the new portfolio (a folder under portfolios/):",
    "portfolio.transactions": "Transactions",
    "portfolio.instruments": "Instruments",
    "portfolio.add_row": "Add transaction",
    "portfolio.kind": "Kind of the new transaction:",
    "portfolio.add_instrument": "Add instrument",
    "portfolio.remove": "Remove selected row",
    "portfolio.start": "Starting position…",
    "portfolio.start_date": "Start date (YYYY-MM-DD):",
    "portfolio.start_added": (
        "Added a transfer in per instrument and a deposit on {day}. Fill in the units, the "
        "market price on that day, your original cost per unit and the cash."
    ),
    "portfolio.save": "Validate and save",
    "portfolio.saved": "Valid and saved: {transactions} transactions, {instruments} instruments.",
    "portfolio.problem": "{table}, row {row}: {error}",
    "portfolio.problem_no_row": "{table}: {error}",
    "portfolio.create_report": "Create report config",
    "portfolio.report_name": "File name for the report config (without .toml):",
    "portfolio.report_created": (
        "{name} created with this portfolio's files. Fill in the price file, its mapping, the "
        "checks and the parameters, then Validate and Run."
    ),
    "portfolio.unsaved": "Portfolio {name} has unsaved changes. Validate and save them?",
    "portfolio.no_selection": "No portfolio is selected.",
    "portfolio.bad_file": "Cannot read {name}: {error}",
    "portfolio.no_transactions": "there are no transactions",
    "portfolio.no_instruments": "Add the instruments first.",
    "portfolio.unknown_isin": "ISIN {isin} is not in the instruments table",
    "portfolio.duplicate_isin": "ISIN {isin} is listed twice",
    "portfolio.bad_date": "{text} is not a date such as 2026-01-02.",
    "portfolio.save_first": "Validate and save the portfolio first.",
    "portfolio.library": "{error}",
    "data.import": "Import a downloaded file…",
    "data.dataset": "Dataset name for this file (for example prices-world):",
    "data.imported": "{name} imported as {dataset}, unchanged, with its provenance.",
}

_IT = {
    "app.title": "Quant Research Lab",
    "app.title_workspace": "Quant Research Lab — {name}",
    "app.disclaimer": (
        "Analisi a scopo di ricerca, non consulenza finanziaria. Ogni numero viene dalla "
        "libreria qrlab, tramite lo stesso runner della riga di comando."
    ),
    "language.en": "English",
    "language.it": "Italiano",
    "nav.home": "Home",
    "nav.portfolios": "Portafogli",
    "nav.portfolio": "Report di portafoglio",
    "nav.risk": "Rischio",
    "nav.scenarios": "Scenari",
    "nav.projections": "Proiezioni",
    "nav.optimiser": "Ottimizzatore",
    "nav.backtests": "Backtest e studi",
    "nav.data": "Dati",
    "nav.history": "Cronologia",
    "nav.settings": "Impostazioni",
    "home.open": "Apri workspace…",
    "home.create": "Crea workspace…",
    "home.none": "Nessun workspace aperto.",
    "home.current": "Workspace: {path}",
    "home.recent": "Workspace recenti",
    "home.missing": "{path} (non trovato)",
    "screen.configs": "Configurazioni",
    "screen.new": "Nuova da modello",
    "screen.duplicate": "Duplica",
    "screen.refresh": "Aggiorna",
    "screen.save": "Salva",
    "screen.validate": "Valida",
    "screen.run": "Esegui",
    "screen.open_report": "Apri report",
    "screen.open_folder": "Apri cartella",
    "screen.no_workspace": "Apri prima un workspace (Home).",
    "screen.new_name": "Nome del file della nuova configurazione (senza .toml):",
    "screen.kind": "Tipo della nuova configurazione:",
    "screen.overwrite": (
        "{name} ha già i risultati di un'esecuzione precedente. Vuoi sostituirli?"
    ),
    "screen.unsaved": "{name} ha modifiche non salvate. Vuoi salvarle?",
    "screen.running": "In esecuzione… {seconds} s",
    "screen.done": "Esecuzione terminata: {status}.",
    "screen.failed": "Non riuscita: {error}",
    "screen.valid": "Valida: {name} ({kind}).",
    "screen.invalid": "Non valida: {error}",
    "screen.busy": "È già in corso un'altra esecuzione.",
    "results.scalars": "Valori",
    "results.figures": "Grafici",
    "results.scalar_columns": "Nome|Valore|Campione",
    "data.columns": (
        "Fonte|Dataset|Scaricato il|Età (giorni)|Più recente|Byte|SHA-256|Condizioni d'uso"
    ),
    "data.latest": "sì",
    "history.columns": "Terminata|Nome|Tipo|Stato|Configurazioni|Cartella|Errore",
    "history.open": "Apri cartella",
    "settings.language": "Lingua",
    "settings.recent": "Workspace recenti",
    "settings.remove": "Rimuovi",
    "settings.clear": "Svuota",
    "settings.about": "Informazioni",
    "settings.version": "Quant Research Lab {version} — Python {python}, Qt {qt}",
    "settings.file": "Le impostazioni sono salvate in {path}.",
    "settings.busy": "Non si può cambiare lingua durante un'esecuzione.",
    "close.busy": (
        "È in corso un'esecuzione che non si può interrompere. Attendi che finisca, poi "
        "chiudi l'app."
    ),
    "tag.in_sample": "in campione",
    "tag.out_of_sample": "fuori campione",
    "tag.descriptive": "descrittivo",
    "status.success": "riuscita",
    "status.failure": "non riuscita",
    "error.no_record": "Nessun record.json in {folder}: l'esecuzione non è terminata.",
    "error.not_folder": "{folder} non è una cartella.",
    "error.workspace": "Impossibile usare {folder} come workspace: {message}",
    "error.unknown_kinds": "Tipi sconosciuti: {kinds}.",
    "error.not_on_screen": "{kind} non è mostrato in questa schermata.",
    "error.no_selection": "Nessuna configurazione selezionata.",
    "error.bad_name": "{name} non è un nome di file valido.",
    "error.exists": "{name} esiste già.",
    "error.language": "Lingua non supportata: {code}.",
    "error.import": "Impossibile importare {name}: {message}",
    "portfolio.list": "Portafogli",
    "portfolio.new": "Nuovo portafoglio",
    "portfolio.new_name": "Nome del nuovo portafoglio (una cartella in portfolios/):",
    "portfolio.transactions": "Transazioni",
    "portfolio.instruments": "Strumenti",
    "portfolio.add_row": "Aggiungi transazione",
    "portfolio.kind": "Tipo della nuova transazione:",
    "portfolio.add_instrument": "Aggiungi strumento",
    "portfolio.remove": "Rimuovi la riga selezionata",
    "portfolio.start": "Posizione di partenza…",
    "portfolio.start_date": "Data di partenza (AAAA-MM-GG):",
    "portfolio.start_added": (
        "Aggiunti un trasferimento in entrata per strumento e un versamento il {day}. Inserisci "
        "le quote, il prezzo di mercato di quel giorno, il tuo costo medio per quota e la "
        "liquidità."
    ),
    "portfolio.save": "Valida e salva",
    "portfolio.saved": "Valido e salvato: {transactions} transazioni, {instruments} strumenti.",
    "portfolio.problem": "{table}, riga {row}: {error}",
    "portfolio.problem_no_row": "{table}: {error}",
    "portfolio.create_report": "Crea la config del report",
    "portfolio.report_name": "Nome del file della config del report (senza .toml):",
    "portfolio.report_created": (
        "{name} creata con i file di questo portafoglio. Inserisci il file dei prezzi, il suo "
        "mapping, i controlli e i parametri, poi Valida ed Esegui."
    ),
    "portfolio.unsaved": "Il portafoglio {name} ha modifiche non salvate. Validarle e salvarle?",
    "portfolio.no_selection": "Nessun portafoglio selezionato.",
    "portfolio.bad_file": "Impossibile leggere {name}: {error}",
    "portfolio.no_transactions": "non ci sono transazioni",
    "portfolio.no_instruments": "Aggiungi prima gli strumenti.",
    "portfolio.unknown_isin": "l'ISIN {isin} non è nella tabella degli strumenti",
    "portfolio.duplicate_isin": "l'ISIN {isin} compare due volte",
    "portfolio.bad_date": "{text} non è una data come 2026-01-02.",
    "portfolio.save_first": "Prima valida e salva il portafoglio.",
    "portfolio.library": "{error}",
    "data.import": "Importa un file scaricato…",
    "data.dataset": "Nome del dataset per questo file (per esempio prezzi-world):",
    "data.imported": "{name} importato come {dataset}, senza modifiche, con la sua provenienza.",
}

STRINGS: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {"en": MappingProxyType(_EN), "it": MappingProxyType(_IT)}
)


def tr(key: str, language: str, **values: object) -> str:
    """Return the string ``key`` in ``language`` with ``{placeholders}`` filled in."""
    if language not in STRINGS:
        raise KeyError(f"unsupported language {language!r}; supported: {list(STRINGS)}")
    return STRINGS[language][key].format(**values)


def tr_value(prefix: str, value: str, language: str) -> str:
    """Translate a recorded value such as a tag or a status; unknown values are shown as is."""
    key = f"{prefix}.{value}"
    return tr(key, language) if key in STRINGS["en"] else value
