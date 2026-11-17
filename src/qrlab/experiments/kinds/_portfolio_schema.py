"""The schema of the ``portfolio_report`` kind: its inputs and every ``[parameters]`` key (12.1).

It describes what the kind's parsers accept (``portfolio_report._parse``, ``parse_risk``,
``parse_projection``, ``parse_distributions``, ``parse_benchmark`` and the tax regimes'
``parse``), never more strictly. The rules that tie keys together (pairs given together,
inputs matching the per-fund tables, a base currency fixed by the tax country) stay in the
parsers and ``_check_inputs``.
"""

from __future__ import annotations

from qrlab.experiments.kinds._fields import (
    COVARIANCE,
    boolean,
    choice,
    currency,
    day,
    file,
    group,
    integer,
    listing,
    mapping,
    moment,
    number,
    records,
    table,
    text,
    variant,
)
from qrlab.experiments.kinds._portfolio_risk import BACKTEST_MODELS
from qrlab.experiments.schema import Field, FieldKind, InputSpec, KindSchema
from qrlab.tax.italy import Regime
from qrlab.tax.italy_wealth import Statements, Where

__all__ = ["SCHEMA"]

_FRACTION = "fraction"

# --------------------------------------------------------------------------- inputs
_INPUTS: tuple[InputSpec, ...] = (
    file(
        "transactions",
        "The transactions: a broker export (mapped) or a native qrlab transactions file.",
        "Le operazioni: un export del broker (mapped) o un file di operazioni nativo di qrlab.",
    ),
    file(
        "prices",
        "The price file (CSV or xlsx), read with prices_mapping; columns are ISINs.",
        "Il file dei prezzi (CSV o xlsx), letto con prices_mapping; le colonne sono ISIN.",
    ),
    file(
        "prices_mapping",
        "The mapping (TOML) of the prices file.",
        "La mappatura (TOML) del file dei prezzi.",
    ),
    file(
        "instruments",
        "The instruments file (TOML): master data of every instrument.",
        "Il file degli strumenti (TOML): anagrafica di ogni strumento.",
    ),
    file(
        "checks",
        "The health-check thresholds (TOML).",
        "Le soglie dei controlli di salute (TOML).",
    ),
    file(
        "transactions_mapping",
        "The mapping (TOML) of a broker export; only with transactions_format = mapped.",
        "La mappatura (TOML) dell'export del broker; solo con transactions_format = mapped.",
        required=False,
    ),
    file(
        "fx",
        "The ECB eurofxref-hist zip; with fx_max_age_days. Absent: every amount in base currency.",
        "Lo zip eurofxref-hist della BCE; con fx_max_age_days. Assente: tutto in valuta base.",
        required=False,
    ),
    file(
        "issuers",
        "A CSV isin,issuer grouping securities by issuer; only with holdings files.",
        "Un CSV isin,issuer che raggruppa i titoli per emittente; solo con i file delle "
        "partecipazioni.",
        required=False,
    ),
    file(
        "scenarios",
        "The stress scenarios (TOML); only with [parameters.risk]. Absent: no scenarios.",
        "Gli scenari di stress (TOML); solo con [parameters.risk]. Assente: nessuno scenario.",
        required=False,
    ),
    file(
        "estr",
        "The ECB €STR file, for the risk-free rate and the Sharpe ratio; needs monthly returns.",
        "Il file €STR della BCE, per il tasso privo di rischio e lo Sharpe; richiede rendimenti "
        "mensili.",
        required=False,
    ),
    file(
        "total_returns",
        "A price file of total-return series per held position, with total_returns_mapping.",
        "Un file di serie total return per posizione detenuta, con total_returns_mapping.",
        required=False,
    ),
    file(
        "total_returns_mapping",
        "The mapping (TOML) of the total_returns file.",
        "La mappatura (TOML) del file total_returns.",
        required=False,
    ),
    file(
        "benchmark",
        "A price file with one total-return column, with [parameters.benchmark]. Absent: none.",
        "Un file prezzi con una colonna total return, con [parameters.benchmark]. Assente: "
        "nessuno.",
        required=False,
    ),
    file(
        "benchmark_mapping",
        "The mapping (TOML) of the benchmark file.",
        "La mappatura (TOML) del file del benchmark.",
        required=False,
    ),
    file(
        "factors",
        "Total-return factor levels for the stress-test proxies, with [parameters.risk.proxies].",
        "Livelli total return dei fattori per i proxy degli stress test, con "
        "[parameters.risk.proxies].",
        required=False,
    ),
    file(
        "factors_mapping",
        "The mapping (TOML) of the factors file.",
        "La mappatura (TOML) del file dei fattori.",
        required=False,
    ),
    group(
        "extra_prices",
        "More price files, one per key (e.g. usd), each with its extra_prices_mapping.",
        "Altri file prezzi, uno per chiave (ad esempio usd), ciascuno con la sua "
        "extra_prices_mapping.",
    ),
    group(
        "extra_prices_mapping",
        "The mapping (TOML) of each extra price file, with the same keys.",
        "La mappatura (TOML) di ogni file prezzi aggiuntivo, con le stesse chiavi.",
    ),
    group(
        "holdings",
        "A fund's holdings file (CSV or xlsx) per fund ISIN, for the look-through.",
        "Il file delle partecipazioni (CSV o xlsx) per ISIN del fondo, per il look-through.",
    ),
    group(
        "holdings_mapping",
        "The mapping (TOML) of each holdings file, with the same ISINs.",
        "La mappatura (TOML) di ogni file delle partecipazioni, con gli stessi ISIN.",
    ),
    group(
        "tracking",
        "Per fund ISIN, a price file with two columns: the fund and its index.",
        "Per ISIN del fondo, un file prezzi con due colonne: il fondo e il suo indice.",
    ),
    group(
        "tracking_mapping",
        "The mapping (TOML) of each tracking file, with the same ISINs.",
        "La mappatura (TOML) di ogni file di tracking, con gli stessi ISIN.",
    ),
)


# --------------------------------------------------------------------------- shared pieces
def _rate(key: str, en: str, it: str) -> Field:
    """Describe a rate in [0, 1), as the tax regimes read it."""
    return number(key, en, it, minimum=0.0, maximum=1.0, open_maximum=True, unit=_FRACTION)


def _moments(key: str, en: str, it: str, *, required: bool = True) -> Field:
    return table(
        key,
        en,
        it,
        (
            number(
                "mean",
                "Mean log return per period.",
                "Rendimento logaritmico medio per periodo.",
            ),
            number(
                "volatility",
                "Volatility of the log return per period.",
                "Volatilità del rendimento logaritmico per periodo.",
                minimum=0.0,
            ),
        ),
        required=required,
    )


# --------------------------------------------------------------------------- per fund
_HOLDINGS = mapping(
    "holdings",
    "Per fund ISIN with a holdings file: the holdings' date and how they are reported. Absent: "
    "no look-through holdings.",
    "Per ISIN del fondo con file delle partecipazioni: data e modalità di rilevazione. "
    "Assente: nessuna partecipazione nel look-through.",
    FieldKind.ISIN,
    table(
        "fund",
        "The holdings of one fund.",
        "Le partecipazioni di un fondo.",
        (
            day(
                "as_of",
                "Date of the holdings, never after the report date.",
                "Data delle partecipazioni, mai dopo la data del report.",
            ),
            text(
                "weight_basis",
                "How the weights are stated, e.g. market value, % of NAV.",
                "Come sono espressi i pesi, ad esempio valore di mercato, % del NAV.",
            ),
            text(
                "sector_taxonomy",
                "The sector classification used, or none.",
                "La classificazione settoriale usata, oppure none.",
            ),
        ),
    ),
    required=False,
)
_TRACKING = mapping(
    "tracking",
    "Per fund ISIN with a tracking file: the index's hedge currency. Absent: no tracking.",
    "Per ISIN del fondo con file di tracking: la valuta di copertura dell'indice. Assente: "
    "nessun tracking.",
    FieldKind.ISIN,
    table(
        "fund",
        "The tracking of one fund.",
        "Il tracking di un fondo.",
        (
            text(
                "index_hedged_to",
                "Currency code the index is hedged to, or none.",
                "Codice della valuta in cui l'indice è coperto, oppure none.",
            ),
        ),
        allow_empty=True,  # an empty table then names the missing key
    ),
    required=False,
)
_DISTRIBUTIONS = mapping(
    "distributions",
    "Per fund ISIN, the distributions that adjust its prices for returns. Absent: prices are "
    "used as they are.",
    "Per ISIN del fondo, le distribuzioni che correggono i prezzi per i rendimenti. Assente: "
    "si usano i prezzi così come sono.",
    FieldKind.ISIN,
    records(
        "payments",
        "The fund's distributions, one per ex-date.",
        "Le distribuzioni del fondo, una per data di stacco.",
        (
            day("ex_date", "Ex-dividend date.", "Data di stacco."),
            number(
                "per_unit",
                "Gross amount per unit, in the price file's currency.",
                "Importo lordo per quota, nella valuta del file dei prezzi.",
                minimum=0.0,
                open_minimum=True,
                unit="currency units",
            ),
            currency("currency", "Currency of the amount.", "Valuta dell'importo."),
        ),
    ),
    required=False,
)
_BENCHMARK = table(
    "benchmark",
    "The benchmark compared with the TWR, with the benchmark inputs. Absent: no benchmark.",
    "Il benchmark confrontato con il TWR, con i file del benchmark. Assente: nessun benchmark.",
    (text("name", "Name of the benchmark in the report.", "Nome del benchmark nel report."),),
    allow_empty=True,  # an empty table then names the missing key
    required=False,
)

# --------------------------------------------------------------------------- risk
_RISK = table(
    "risk",
    "Risk and stress tests of today's weights on past returns. Absent: no risk section.",
    "Rischio e stress test dei pesi di oggi sui rendimenti passati. Assente: nessuna sezione "
    "di rischio.",
    (
        choice(
            "frequency",
            "Frequency of the returns: weekly or monthly.",
            "Frequenza dei rendimenti: settimanale o mensile.",
            ("weekly", "monthly"),
        ),
        integer(
            "window",
            "Number of most recent returns used.",
            "Numero dei rendimenti più recenti usati.",
            minimum=2,
            unit="periods",
        ),
        number(
            "confidence",
            "Confidence of the VaR and ES, between 0.5 and 1 (e.g. 0.95).",
            "Confidenza di VaR ed ES, tra 0,5 e 1 (ad esempio 0,95).",
            minimum=0.5,
            maximum=1.0,
            open_minimum=True,
            open_maximum=True,
            unit=_FRACTION,
        ),
        COVARIANCE,
        table(
            "backtest",
            "Backtest of the VaR model on today's weights. Absent: no backtest.",
            "Backtest del modello VaR sui pesi di oggi. Assente: nessun backtest.",
            (
                integer(
                    "window",
                    "Returns used for each forecast.",
                    "Rendimenti usati per ogni previsione.",
                    minimum=2,
                    unit="periods",
                ),
                choice(
                    "model",
                    "The VaR model: historical, normal or cornish_fisher.",
                    "Il modello VaR: historical, normal o cornish_fisher.",
                    BACKTEST_MODELS,
                ),
            ),
            required=False,
        ),
        mapping(
            "proxies",
            "Per ISIN without its own history, its betas to the factors, with the factors "
            "inputs. Absent: no proxies.",
            "Per ISIN senza storia propria, i beta verso i fattori, con i file dei fattori. "
            "Assente: nessun proxy.",
            FieldKind.ISIN,
            mapping(
                "betas",
                "Factor name = beta.",
                "Nome del fattore = beta.",
                FieldKind.TEXT,
                number("beta", "Beta to the factor.", "Beta verso il fattore."),
            ),
            required=False,
        ),
    ),
    required=False,
)

# --------------------------------------------------------------------------- projection
_ENGINE = variant(
    "engine",
    "How returns are simulated: normal, or student_t with its degrees of freedom.",
    "Come si simulano i rendimenti: normal, oppure student_t con i suoi gradi di libertà.",
    "name",
    {
        "normal": (),
        "student_t": (
            number(
                "dof",
                "Degrees of freedom of the Student t.",
                "Gradi di libertà della t di Student.",
            ),
        ),
    },
)
_FLOWS = records(
    "flows",
    "The savings plan: contributions and withdrawals (empty for none).",
    "Il piano: versamenti e prelievi (vuoto per nessuno).",
    (
        choice(
            "kind",
            "contribution or withdrawal.",
            "contribution (versamento) o withdrawal (prelievo).",
            ("contribution", "withdrawal"),
        ),
        number(
            "amount",
            "Amount per period, in base currency.",
            "Importo per periodo, in valuta base.",
            unit="currency units",
        ),
        integer(
            "first",
            "First period of the flow (0 is the first).",
            "Primo periodo del flusso (0 è il primo).",
            minimum=0,
            unit="periods",
        ),
        integer(
            "last",
            "Last period of the flow.",
            "Ultimo periodo del flusso.",
            minimum=0,
            unit="periods",
        ),
        boolean(
            "indexed",
            "Whether the amount grows with inflation.",
            "Se l'importo cresce con l'inflazione.",
        ),
    ),
    allow_empty=True,
)
_PROJECTION = table(
    "projection",
    "Monte Carlo projection of today's portfolio under stated assumptions. Absent: no projection.",
    "Proiezione Monte Carlo del portafoglio di oggi con ipotesi dichiarate. Assente: nessuna "
    "proiezione.",
    (
        integer(
            "seed",
            "Seed of the random numbers, for a reproducible run.",
            "Seme dei numeri casuali, per un risultato riproducibile.",
            minimum=0,
        ),
        _ENGINE,
        integer("paths", "Number of simulated paths.", "Numero di percorsi simulati.", minimum=10),
        integer(
            "periods",
            "Number of periods projected.",
            "Numero di periodi proiettati.",
            minimum=1,
            unit="periods",
        ),
        integer(
            "periods_per_year",
            "Periods in a year (12 for monthly).",
            "Periodi in un anno (12 per mensile).",
            minimum=1,
            unit="periods",
        ),
        number(
            "goal_real",
            "Goal for the final wealth, in today's money.",
            "Obiettivo per la ricchezza finale, in moneta di oggi.",
            unit="currency units",
        ),
        listing(
            "percentiles",
            "Percentiles shown in the fan chart, e.g. 5, 50, 95.",
            "Percentili mostrati nel grafico a ventaglio, ad esempio 5, 50, 95.",
            number("percentile", "A percentile.", "Un percentile."),
        ),
        integer(
            "early_periods",
            "Periods counted as early for the depletion statistics.",
            "Periodi considerati iniziali per le statistiche di esaurimento.",
            minimum=1,
            unit="periods",
        ),
        integer(
            "rebalance_every",
            "Periods between rebalancings; 0 for never.",
            "Periodi tra due ribilanciamenti; 0 per mai.",
            minimum=0,
            unit="periods",
        ),
        choice(
            "flow_timing",
            "Whether flows happen at the start or the end of each period.",
            "Se i flussi avvengono all'inizio o alla fine di ogni periodo.",
            ("start", "end"),
        ),
        number(
            "annual_cost",
            "Yearly cost as a fraction of value, or ter for the weighted TER of the instruments.",
            "Costo annuo come frazione del valore, oppure ter per il TER ponderato degli "
            "strumenti.",
            unit=_FRACTION,
            also=("ter",),
        ),
        number(
            "inflation",
            "Yearly inflation rate.",
            "Tasso di inflazione annuo.",
            unit=_FRACTION,
        ),
        number(
            "capital_gains_tax",
            "Tax rate on realised gains.",
            "Aliquota sulle plusvalenze realizzate.",
            unit=_FRACTION,
        ),
        number(
            "wealth_tax",
            "Yearly tax rate on value.",
            "Aliquota annua sul patrimonio.",
            unit=_FRACTION,
        ),
        _FLOWS,
        mapping(
            "assets",
            "Per held position (ISIN), its return assumptions.",
            "Per posizione detenuta (ISIN), le ipotesi di rendimento.",
            FieldKind.ISIN,
            _moments(
                "asset",
                "Return assumptions of one position.",
                "Ipotesi di rendimento di una posizione.",
            ),
        ),
        _moments(
            "cash",
            "Return assumptions of cash; needed when the portfolio holds cash. Absent: no cash.",
            "Ipotesi di rendimento della liquidità; serve se il portafoglio ne detiene. "
            "Assente: nessuna liquidità.",
            required=False,
        ),
        mapping(
            "correlations",
            'Correlation of each pair of risky assets, keyed "ISIN1 ISIN2" (or with cash). '
            "Absent: none given.",
            'Correlazione di ogni coppia di attività rischiose, con chiave "ISIN1 ISIN2" (o con '
            "cash). Assente: nessuna.",
            FieldKind.TEXT,
            number(
                "correlation",
                "A correlation between -1 and 1.",
                "Una correlazione tra -1 e 1.",
                minimum=-1.0,
                maximum=1.0,
            ),
            allow_empty=True,
            required=False,
        ),
        number(
            "income_tax_rate",
            "Tax rate on the taxable yield; with taxable_yield. Absent: no income tax.",
            "Aliquota sul rendimento imponibile; con taxable_yield. Assente: nessuna imposta sul "
            "reddito.",
            unit=_FRACTION,
            required=False,
        ),
        number(
            "taxable_yield",
            "Yearly taxable yield on value; with income_tax_rate. Absent: no income tax.",
            "Rendimento imponibile annuo sul valore; con income_tax_rate. Assente: nessuna "
            "imposta sul reddito.",
            unit=_FRACTION,
            required=False,
        ),
        table(
            "losses",
            "Losses carried forward against gains (the held funds are the fund assets). Absent: "
            "losses are not netted.",
            "Minusvalenze riportate contro le plusvalenze (i fondi detenuti sono le attività "
            "fondo). Assente: le minusvalenze non si compensano.",
            (
                integer(
                    "carry_years",
                    "Years a loss can be carried forward.",
                    "Anni per cui una minusvalenza si può riportare.",
                    minimum=0,
                    unit="years",
                ),
            ),
            allow_empty=True,  # an empty table then names the missing key
            required=False,
        ),
    ),
    required=False,
)

# --------------------------------------------------------------------------- tax
_ITALY = (
    choice(
        "regime",
        "The account's tax regime: amministrato or dichiarativo.",
        "Il regime fiscale del conto: amministrato o dichiarativo.",
        tuple(r.value for r in Regime),
    ),
    mapping(
        "public_share",
        "Per ISIN, the share of Italian and white-list government bonds (0 for an equity fund).",
        "Per ISIN, la quota di titoli di Stato italiani e white list (0 per un fondo azionario).",
        FieldKind.ISIN,
        number(
            "share",
            "A share between 0 and 1.",
            "Una quota tra 0 e 1.",
            minimum=0.0,
            maximum=1.0,
            unit=_FRACTION,
        ),
        allow_empty=True,
    ),
    mapping(
        "custody",
        "Per account, where it is held, for the stamp duty and the IVAFE. Absent: no wealth taxes.",
        "Per conto, dove è detenuto, per l'imposta di bollo e l'IVAFE. Assente: nessuna imposta "
        "patrimoniale.",
        FieldKind.TEXT,
        variant(
            "account",
            "Where one account is held.",
            "Dove è detenuto un conto.",
            "where",
            {
                Where.ITALY.value: (
                    choice(
                        "statements",
                        "How often the intermediary sends statements: year, quarter or month.",
                        "Ogni quanto l'intermediario invia gli estratti: year, quarter o month.",
                        tuple(s.value for s in Statements),
                    ),
                ),
                Where.ABROAD.value: (
                    number(
                        "share",
                        "The investor's share of the account, above 0 and up to 1.",
                        "La quota del conto dell'investitore, sopra 0 e fino a 1.",
                        minimum=0.0,
                        maximum=1.0,
                        open_minimum=True,
                        unit=_FRACTION,
                    ),
                ),
                Where.ABROAD_PRIVILEGED.value: (
                    number(
                        "share",
                        "The investor's share of the account, above 0 and up to 1.",
                        "La quota del conto dell'investitore, sopra 0 e fino a 1.",
                        minimum=0.0,
                        maximum=1.0,
                        open_minimum=True,
                        unit=_FRACTION,
                    ),
                ),
            },
        ),
        required=False,
    ),
)
_SWITZERLAND = (
    _rate(
        "marginal_rate",
        "Marginal income tax rate, in [0, 1).",
        "Aliquota marginale sul reddito, in [0, 1).",
    ),
    _rate(
        "wealth_tax_rate",
        "Wealth tax rate, in [0, 1).",
        "Aliquota dell'imposta sulla sostanza, in [0, 1).",
    ),
    mapping(
        "net_income",
        "Net income by year (year = amount), for the safe-haven check; may be empty.",
        "Reddito netto per anno (anno = importo), per il controllo safe haven; può essere vuoto.",
        FieldKind.INTEGER,
        number(
            "amount",
            "The year's net income.",
            "Il reddito netto dell'anno.",
            minimum=0.0,
            unit="currency units",
        ),
        allow_empty=True,
    ),
    boolean(
        "debt_financed",
        "Whether the securities are financed with debt.",
        "Se i titoli sono finanziati con debito.",
    ),
    mapping(
        "reported_income",
        "Per ISIN, the income per unit from the ESTV price list; may be empty.",
        "Per ISIN, il reddito per quota dal listino corsi dell'AFC; può essere vuoto.",
        FieldKind.ISIN,
        records(
            "closings",
            "The fund's income at each yearly closing.",
            "Il reddito del fondo a ogni chiusura annuale.",
            (
                day("date", "Date of the closing.", "Data della chiusura."),
                text(
                    "per_unit",
                    'Income per unit, a quoted decimal such as "2.50".',
                    'Reddito per quota, un decimale tra virgolette come "2.50".',
                ),
                currency("currency", "Currency of the amount.", "Valuta dell'importo."),
            ),
            allow_empty=True,
        ),
        allow_empty=True,
    ),
)
_CUSTOM = (
    text(
        "description",
        "What the stated rules describe, shown in the report.",
        "Cosa descrivono le regole indicate, mostrato nel report.",
    ),
    _rate("gains_rate", "Tax rate on gains, in [0, 1).", "Aliquota sulle plusvalenze, in [0, 1)."),
    _rate(
        "income_rate",
        "Tax rate on income, in [0, 1).",
        "Aliquota sui redditi, in [0, 1).",
    ),
    choice(
        "losses",
        "Whether losses are ignored or netted against gains.",
        "Se le minusvalenze si ignorano o si compensano con le plusvalenze.",
        ("ignored", "netted"),
    ),
    integer(
        "loss_carry_years",
        "Years a netted loss can be carried forward (0 when losses are ignored).",
        "Anni per cui una minusvalenza compensata si riporta (0 se si ignorano).",
        minimum=0,
        unit="years",
    ),
    integer(
        "exempt_after_months",
        "Months after which a gain is exempt; 0 for never.",
        "Mesi dopo i quali una plusvalenza è esente; 0 per mai.",
        minimum=0,
        unit="months",
    ),
    number(
        "gains_allowance",
        "Yearly gains exempt from tax.",
        "Plusvalenze annue esenti da imposta.",
        minimum=0.0,
        unit="currency units",
    ),
    _rate(
        "wealth_tax_rate",
        "Wealth tax rate, in [0, 1).",
        "Aliquota dell'imposta patrimoniale, in [0, 1).",
    ),
)
_TAX = variant(
    "tax",
    "Tax position (analytics, not tax advice) under a country's rules. Absent: no tax section.",
    "Posizione fiscale (analisi, non consulenza fiscale) secondo le regole di un paese. "
    "Assente: nessuna sezione fiscale.",
    "country",
    {"it": _ITALY, "ch": _SWITZERLAND, "custom": _CUSTOM},
    required=False,
)

# --------------------------------------------------------------------------- the schema
SCHEMA = KindSchema(
    inputs=_INPUTS,
    parameters=(
        choice(
            "transactions_format",
            "How transactions is read: mapped (a broker export) or native (a qrlab file).",
            "Come si legge transactions: mapped (export del broker) o native (file di qrlab).",
            ("mapped", "native"),
        ),
        text("title", "Title of the report.", "Titolo del report."),
        currency(
            "base_currency",
            "Currency the portfolio is valued in.",
            "Valuta in cui è valutato il portafoglio.",
        ),
        choice("language", "Language of the report.", "Lingua del report.", ("it", "en")),
        choice(
            "flow_timing",
            "Whether external flows count at the start or the end of their day.",
            "Se i flussi esterni contano all'inizio o alla fine della loro giornata.",
            ("start", "end"),
        ),
        integer(
            "max_price_age_days",
            "Oldest acceptable price, in calendar days.",
            "Prezzo più vecchio accettato, in giorni di calendario.",
            minimum=0,
            unit="days",
        ),
        choice(
            "return_frequency",
            "Frequency of the TWR returns shown: monthly or none.",
            "Frequenza dei rendimenti TWR mostrati: monthly o none.",
            ("monthly", "none"),
        ),
        moment(
            "generated_at",
            "When the report is dated, with a time zone.",
            "Data e ora del report, con fuso orario.",
        ),
        mapping(
            "target_weights",
            "Target weight per ISIN or cash, for the drift checks; empty for none.",
            "Peso obiettivo per ISIN o cash, per i controlli di scostamento; vuoto per nessuno.",
            FieldKind.TEXT,
            number("weight", "A target weight.", "Un peso obiettivo.", unit=_FRACTION),
            allow_empty=True,
        ),
        integer(
            "fx_max_age_days",
            "Oldest acceptable ECB rate, in calendar days; with the fx input. Absent: no fx.",
            "Cambio BCE più vecchio accettato, in giorni di calendario; con il file fx. "
            "Assente: nessun cambio.",
            minimum=0,
            unit="days",
            required=False,
        ),
        choice(
            "lookthrough_treatment",
            "How fund holdings are weighed: as_reported or normalised; with holdings files.",
            "Come si pesano le partecipazioni dei fondi: as_reported o normalised; con i file "
            "delle partecipazioni.",
            ("as_reported", "normalised"),
            required=False,
        ),
        _HOLDINGS,
        _TRACKING,
        _RISK,
        _PROJECTION,
        _TAX,
        _DISTRIBUTIONS,
        _BENCHMARK,
    ),
)
