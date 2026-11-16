"""Report labels in Italian and English. Both languages must define the same keys (tested)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from qrlab.reporting.formatting import Language

__all__ = ["LABELS", "label"]

_EN = {
    "report_title": "Portfolio report",
    "base_currency": "Base currency",
    "period": "Period",
    "generated_at": "Generated at",
    "as_of": "Data as of",
    "warnings": "Warnings",
    "summary": "Summary",
    "end_value": "End value",
    "net_flows": "Net external flows",
    "pnl": "Profit and loss",
    "twr": "Time-weighted return (TWR)",
    "twr_definition": "Measures the investments, neutralising deposits and withdrawals.",
    "twr_annualised": "TWR, annualised",
    "mwr": "Money-weighted return (MWR, XIRR, a year)",
    "mwr_definition": "Measures the investor's experience, including the timing of flows.",
    "not_comparable": "TWR and MWR measure different things and are not comparable.",
    "max_drawdown": "Maximum drawdown (TWR path)",
    "volatility": "Volatility, annualised",
    "volatility_omitted": "Volatility is omitted: no regular return frequency was declared.",
    "risk_free_total": "Risk-free return over the period ({source})",
    "sharpe": "Sharpe ratio (TWR in excess of the risk-free rate, annualised)",
    "sharpe_value": "{value} ± {se} (n = {n})",
    "sharpe_missing": "The Sharpe ratio is not shown: {reason}",
    "tax_title": "Tax position (analytics, not tax advice)",
    "tax_intro": "Account in the {regime} regime. Rules as checked on {checked}.",
    "tax_regime_amministrato": "amministrato (the broker withholds the tax)",
    "tax_regime_dichiarativo": "dichiarativo (you declare the tax)",
    "tax_rules": (
        "Gains on ETFs and funds are capital income, taxed in full; losses on them and results "
        "on shares, bonds and ETCs are other income. Losses offset only other income, oldest "
        "first, until 31 December of the fourth following year. The share due to government "
        "bonds counts for 48.08 %."
    ),
    "tax_estimate": "Nothing is withheld in this regime: the tax shown is an estimate to declare.",
    "tax_flagged": (
        "Not computed: {names}. Funds domiciled outside the EU and EEA are taxed at progressive"
        " income-tax rates."
    ),
    "tax_sources": "Sources: {sources}.",
    "tax_events": "Sales and their tax",
    "tax_events_note": (
        "Result: net of fees, before tax. Base: after the government-bond share. Difference: "
        "tax withheld minus tax due; a difference is shown, never absorbed."
    ),
    "tax_category": "Category",
    "tax_cat_redditi_di_capitale": "Capital income",
    "tax_cat_redditi_diversi": "Other income",
    "tax_cat_not_computed": "Not computed",
    "tax_result": "Result",
    "tax_public_share": "Government bonds",
    "tax_base": "Base",
    "tax_offset": "Losses used",
    "tax_due": "Tax due",
    "tax_withheld": "Tax withheld",
    "tax_difference": "Difference",
    "tax_totals": "Totals",
    "tax_losses_remaining": "Losses still usable",
    "tax_losses": "Losses balance (zainetto) by year",
    "tax_year": "Year",
    "tax_amount": "Losses",
    "tax_used": "Used",
    "tax_expired": "Expired",
    "tax_remaining": "Remaining",
    "tax_usable_until": "Usable until",
    # --- Switzerland (phase 9.2) ----------------------------------------------------------
    "ch_intro": (
        "Private investor resident in Switzerland. Rules as checked on {checked}. Taxes are "
        "estimates at the rates you stated, not an assessment."
    ),
    "ch_gains_rule": (
        "Gains on private wealth are not taxed, unless the investor counts as a professional "
        "securities trader."
    ),
    "ch_safe_haven_rule": (
        "The ESTV Circular 36 criteria are checked for each year. When all five are met, "
        "professional trading is excluded; otherwise it cannot be excluded, and the tax office "
        "judges the whole case."
    ),
    "ch_first_year": (
        "{year}: the volume is compared with the account's first valuation, as there is none "
        "before."
    ),
    "ch_income_rule": (
        "Dividends and interest are income at their gross amount. An accumulating fund's "
        "reinvested income is taxed every year, at its yearly closing, from the price-list "
        "amount per unit you gave."
    ),
    "ch_withholding_rule": (
        "The 35 % Swiss withholding tax on Swiss instruments is refunded when the income is "
        "declared. Tax withheld abroad, or on interest without an instrument, is listed but "
        "not classified."
    ),
    "ch_wealth_rule": (
        "Wealth is the account's value on the last valuation of each year; the ESTV price "
        "list's year-end prices may differ slightly."
    ),
    "ch_settings": "Rates you stated",
    "ch_marginal_rate": "Marginal income-tax rate",
    "ch_wealth_tax_rate": "Wealth-tax rate",
    "ch_years": "Tax position by year",
    "ch_gains": "Realised gains",
    "ch_income": "Taxable income",
    "ch_income_tax": "Income tax (estimate)",
    "ch_refundable": "Withholding tax refundable",
    "ch_wealth": "Wealth at year end",
    "ch_wealth_tax": "Wealth tax (estimate)",
    "ch_year_open": "year not ended",
    "ch_safe_haven": "Circular 36",
    "ch_conclusion_met": "safe haven met",
    "ch_conclusion_not_excluded": "professional trading not excluded",
    "ch_conclusion_incomplete": "incomplete (inputs missing)",
    "ch_criterion": "Criterion",
    "ch_criterion_holding": "Holding period of the units sold, at least 6 months",
    "ch_criterion_volume": "Purchases and sales, at most 5 x the value at the start",
    "ch_criterion_gains": "Realised gains, below 50 % of net income",
    "ch_criterion_debt": "Not financed by debt",
    "ch_criterion_derivatives": "Derivatives only to hedge",
    "ch_limit": "Limit",
    "ch_detail": "Shortest holding",
    "ch_result": "Result",
    "ch_result_met": "met",
    "ch_result_not_met": "not met",
    "ch_result_not_checked": "not checked (input missing)",
    "ch_safe_haven_note": (
        "Holding periods are taken first in, first out. A debt-financed account needs your "
        "interest expense, which qrlab does not have."
    ),
    "ch_income_items": "Income",
    "ch_income_note": "Amounts in CHF, converted on each date.",
    "ch_income_kind": "Kind",
    "ch_income_dividend": "dividend",
    "ch_income_interest": "interest",
    "ch_income_reported_income": "fund income (price list)",
    "ch_cash": "cash",
    "ch_units": "Units",
    "ch_per_unit": "Per unit",
    "ch_gross": "Gross",
    # --- the configurable model (phase 9.3) -----------------------------------------------
    "custom_title": "Tax estimate: a simplified model you configured, not a country's law",
    "custom_intro": (
        "Model: {description}. The rules are the ones you stated; no country's law is "
        "applied. Taxes are estimates."
    ),
    "custom_order": (
        "Per calendar year: each sale's result at average cost; the exempt part by holding "
        "period; losses; the allowance; then the rates."
    ),
    "custom_losses_netted": (
        "Losses are netted with the year's gains; a net loss can be used in the {years} "
        "following year(s), oldest first."
    ),
    "custom_losses_ignored": "Losses are ignored: each gain is taxed alone.",
    "custom_exempt": (
        "Gains on units held at least {months} months are exempt; the units sold are matched "
        "first in, first out, an approximation next to the average cost."
    ),
    "custom_no_exempt": "No gain is exempt by holding period.",
    "custom_withheld": (
        "Tax withheld on income is shown next to the income tax, not credited: whether it "
        "can be depends on the country and the treaty."
    ),
    "custom_gains_rate": "Gains-tax rate",
    "custom_income_rate": "Income-tax rate",
    "custom_wealth_tax_rate": "Wealth-tax rate",
    "custom_allowance": "Yearly gains allowance",
    "custom_settings": "Rates you stated",
    "custom_amounts": "Amounts you stated",
    "custom_years": "Taxes by year (estimates)",
    "custom_years_note": "Your rules, applied as stated; not a country's law.",
    "custom_result": "Realised result",
    "custom_exempt_amount": "Exempt by holding",
    "custom_taxable_gains": "Taxable gains",
    "custom_taxable_losses": "Taxable losses",
    "custom_losses_used": "Losses used",
    "custom_allowance_used": "Allowance used",
    "custom_taxable": "Taxable after losses and allowance",
    "custom_gains_tax": "Gains tax",
    "not_annualised": "Not annualised: the period is shorter than one year.",
    "positions": "Positions",
    "account": "Account",
    "isin": "ISIN",
    "name": "Name",
    "quantity": "Quantity",
    "price": "Price",
    "price_date": "Price date",
    "currency": "Currency",
    "value": "Value",
    "weight": "Weight",
    "cost_basis": "Cost basis",
    "unrealised": "Unrealised P&L",
    "cash": "Cash",
    "local_amount": "Amount",
    "base_amount": "In base currency",
    "pnl_breakdown": "Profit and loss breakdown",
    "realised": "Realised",
    "unrealised_change": "Unrealised (change)",
    "income": "Income (net)",
    "costs": "Costs",
    "cash_fx": "Currency effect on cash",
    "transfers": "Gains carried in or out by transfers",
    "residual": "Residual (should be zero)",
    "income_costs": "Income and costs",
    "date": "Date",
    "kind": "Kind",
    "amount": "Amount",
    "figures": "Charts",
    "figure_value": "Portfolio value",
    "figure_twr": "Cumulative TWR",
    "figure_drawdown": "Drawdown (TWR path)",
    "flows_marker": "External flows",
    "data_assumptions": "Data and assumptions",
    "sources": "Data sources",
    "source": "Source",
    "dataset": "Dataset",
    "retrieved": "Retrieved",
    "sha256": "SHA-256",
    "terms": "Terms",
    "assumptions": "Assumptions",
    "flow_timing": "Flow timing",
    "cost_basis_method": "Cost basis",
    "cost_basis_value": "Weighted average cost including purchase charges",
    "fx_source": "FX conversion",
    "price_staleness": "Maximum price age (days)",
    "carried_forward": "Carried-forward values",
    "requested_date": "Requested",
    "used_date": "Used",
    "import_notes": "Import notes",
    "disclaimer": "Analytics, not investment advice.",
    "private_reminder": "This report may contain personal financial data: keep it private.",
    "version": "qrlab version",
    "warn_stale_price": "Price of {isin} for {requested} taken from {used}.",
    "warn_stale_fx": "{currency} rate for {requested} taken from {used}.",
    "warn_residual": "The profit and loss residual is {value}, not zero: check the inputs.",
    "warn_mwr_roots": "The MWR is not unique: candidate rates {rates}.",
    "warn_missing_master": "No master data for {isin}: the ISIN is shown instead of a name.",
    "warn_skipped": "No TWR for {dates}: zero starting capital.",
    "not_enough_dates": "Not enough valuation dates to compute returns.",
    "none": "None",
    "not_available": "n/a",
    "timing_start_of_day": "Start of day",
    "timing_end_of_day": "End of day",
    "holdings_count": "Positions held",
    "kind_deposit": "Deposit",
    "kind_withdrawal": "Withdrawal",
    "kind_buy": "Buy",
    "kind_sell": "Sell",
    "kind_dividend": "Dividend",
    "kind_interest": "Interest",
    "kind_fee": "Fee",
    "kind_tax": "Tax",
    "kind_fx_conversion": "FX conversion",
    "kind_transfer_in": "Transfer in",
    "kind_transfer_out": "Transfer out",
    "kind_split": "Split",
    "projection": "Projection",
    "projection_not_computed": "No projection was computed for this report.",
    "projection_note": (
        "Projections are scenarios generated from the assumptions below, not forecasts or "
        "advice. Results are distributions; every probability carries its Monte Carlo error."
    ),
    "projection_costs_note": (
        "Fund costs (TER) belong in the return assumptions. The tax model does not carry "
        "losses forward and uses one blended rate: it is an example, not tax advice."
    ),
    "engine": "Return engine",
    "paths": "Simulated paths",
    "horizon": "Horizon",
    "years": "{n} years",
    "initial_wealth": "Initial wealth",
    "flows": "Flows",
    "flow_contribution": "contribution {amount} in periods {first}-{last} ({indexed})",
    "flow_withdrawal": "net withdrawal {amount} in periods {first}-{last} ({indexed})",
    "indexed": "indexed to inflation",
    "fixed": "fixed",
    "timing_start_of_period": "Start of each period",
    "timing_end_of_period": "End of each period",
    "rebalancing": "Rebalancing",
    "rebalance_never": "Never (buy and hold)",
    "rebalance_every": "Every {n} periods",
    "annual_cost": "Annual costs",
    "inflation": "Inflation (a year)",
    "capital_gains_tax": "Capital-gains tax",
    "wealth_tax": "Wealth tax (a year)",
    "terminal_wealth": "Terminal wealth",
    "percentile": "Percentile",
    "real": "Real (today's money)",
    "nominal": "Nominal",
    "after_tax": "Nominal after liquidation tax",
    "after_tax_note": "After-tax values assume everything is sold at the end.",
    "probabilities": "Goal, depletion and sequence risk",
    "goal": "Probability of reaching {goal} (real)",
    "depletion": "Probability of running out",
    "median_depletion": "Median period of running out",
    "mean_terminal_real": "Mean real terminal wealth",
    "sequence_worst": "Median real terminal wealth, worst 10 % of the first {n} periods",
    "sequence_best": "Median real terminal wealth, best 10 % of the first {n} periods",
    "se_note": "± is one Monte Carlo standard error.",
    "sensitivity": "Sensitivity to the assumptions",
    "assumption": "Change",
    "goal_probability": "Goal probability",
    "median_real": "Median real terminal wealth",
    "sensitivity_note": "Each change is run on the same random numbers as the base case.",
    "sens_base": "None (base case)",
    "sens_mean_down": "Mean return -1 point a year",
    "sens_mean_up": "Mean return +1 point a year",
    "sens_vol_down": "Volatility x0.8",
    "sens_vol_up": "Volatility x1.2",
    "sens_inflation_down": "Inflation -1 point",
    "sens_inflation_up": "Inflation +1 point",
    "sens_costs_up": "Costs +0.5 points",
    "sens_costs_down": "Costs -0.5 points",
    "fan_chart": "Projected wealth in today's money (percentiles)",
    "risk_stress": "Risk and stress tests",
    "risk_not_computed": "Risk numbers and stress tests were not computed for this report.",
    "risk_window": (
        "Risk figures are one {frequency} period, estimated on {n} returns from {start} to "
        "{end}; they are not annualised."
    ),
    "stress_note": (
        "Stress tests are 'what if' analyses on today's weights, not forecasts or "
        "probabilities. Proxy replays use factor betas and ignore specific risk."
    ),
    "risk_volatility": "Volatility contributions",
    "holding": "Holding",
    "contribution": "Contribution",
    "share": "Share",
    "total": "Total",
    "risk_var_es": "Value at risk and expected shortfall at {confidence}",
    "method": "Method",
    "var_note": "Positive numbers are losses. No method is 'the' VaR: compare them.",
    "benchmark": "Benchmark",
    "benchmark_none": "No benchmark was given for this report.",
    "benchmark_intro": (
        "Benchmark: {name}, a total-return series in {currency}, valued in {base} with the ECB "
        "rate of each date."
    ),
    "benchmark_no_period": "There is no period between two valuation dates to compare.",
    "benchmark_window": (
        "The comparison uses the {n} periods between valuation dates from {start} to {end}; "
        "a return on the first valuation date (from a deposit to that day's close) is left out."
    ),
    "benchmark_measures": "Portfolio against the benchmark",
    "benchmark_portfolio_total": "Portfolio return over these periods",
    "benchmark_total": "Benchmark return over these periods",
    "benchmark_difference": "Difference (percentage points)",
    "tracking_error": "Tracking error (annualised)",
    "information_ratio": "Information ratio (annualised)",
    "beta": "Beta",
    "beta_excess": "Beta (on excess returns over the risk-free rate)",
    "beta_plain": "Beta (on returns; no risk-free series given)",
    "alpha_annual": "Alpha (annualised)",
    "r_squared": "R squared",
    "observations": "Observations",
    "with_se": "{value} (standard error {se})",
    "benchmark_missing": "{measure}: not available ({reason}).",
    "benchmark_conventions": (
        "Simple returns. Active return = portfolio return - benchmark return, per period. "
        "Annualised from monthly returns with 12 and sqrt(12), which assumes no serial "
        "correlation. Ordinary least squares with classical standard errors. Descriptive: a "
        "short window says little about skill. A benchmark of another universe or a price "
        "index would make these numbers meaningless."
    ),
    "benchmark_carried": "Benchmark: {what}",
    "return_sources": "Returns used for risk",
    "return_series": "Series",
    "income_in_returns": "Income paid out",
    "income_included": "included",
    "income_excluded": "excluded",
    "return_sources_note": (
        "The portfolio is valued at market prices. Risk and the diversification checks read "
        "returns, which include the income a fund pays out only for the series marked so."
    ),
    "return_source_total_return_file": "Total-return series given",
    "return_source_distributions": "Price plus the distributions given",
    "return_source_total_return_prices": "Price file of total returns",
    "return_source_accumulating": "Price of an accumulating fund",
    "return_source_no_income": "Price of an ETC (no income)",
    "return_source_distributing": "Price of a distributing fund",
    "return_source_policy_unknown": "Price (distribution policy unknown)",
    "return_source_stock": "Price of a stock",
    "return_source_bond": "Price of a bond",
    "return_source_other": "Price",
    "scenarios": "Stress scenarios",
    "scenario": "Scenario",
    "dates_used": "Dates used",
    "portfolio_return": "Portfolio return",
    "not_covered": "Not covered",
    "not_covered_note": (
        "Weight that is not covered is excluded from the portfolio figure, never assumed to "
        "lose nothing."
    ),
    "scenario_detail": "Stress scenarios by holding",
    "base_return": "Return in base currency",
    "scenario_historical": "Historical",
    "scenario_hypothetical": "Hypothetical",
    "method_direct": "Own history",
    "method_proxy": "Factor proxy",
    "method_shock": "Direct shock",
    "method_currency_only": "Currency only",
    "method_cash": "Cash",
    "method_not_covered": "Not covered",
    "lookthrough": "Look-through",
    "lookthrough_not_done": "Look-through of fund holdings was not done for this report.",
    "lt_as_reported": (
        "Fund holdings are used as reported: weight the holdings do not explain is shown as "
        "a separate bucket, never spread over the others."
    ),
    "lt_normalised": "Fund holdings are rescaled to sum to 100 % (explicit choice).",
    "lt_buckets": (
        "Unknown values, funds without holdings data and cash are separate buckets; they are "
        "never counted as one country, sector or security."
    ),
    "lt_no_issuer_map": ("No issuer map was given: concentration is per security, not per issuer."),
    "holdings_dates": "Holdings dates",
    "holdings_date": "Holdings as of",
    "age_days": "Age (days)",
    "lt_country": "Country",
    "lt_sector": "Sector",
    "lt_currency": "Currency (after hedging)",
    "lt_security": "Security",
    "lt_more": "{count} smaller entries not shown.",
    "lt_overlap": "Overlap between funds",
    "fund": "Fund",
    "overlap": "Overlap",
    "overlap_by_name": "Of which by name",
    "lt_overlap_note": (
        "Securities are matched by ISIN and, where a fund lists one without an ISIN, by "
        "normalised name. Matches by name are approximate."
    ),
    "unmatched": "Without ISIN",
    "lt_tracking": "Tracking difference",
    "series_type": "Series",
    "series_nav": "NAV",
    "series_total_return": "Total return",
    "series_price": "Price",
    "td_period": "Over the period",
    "td_annualised": "Annualised",
    "ter": "TER",
    "td_plus_ter": "TD + TER",
    "td_note": (
        "Fund return minus index return. Not annualised over less than a year. "
        "TD + TER below zero means costs beyond the TER."
    ),
    "bucket_unknown": "Unknown",
    "bucket_unexplained": "Not explained by the holdings",
    "bucket_not_looked_through": "Funds without holdings data",
    "health_checks": "Health checks",
    "checks_not_run": "Health checks were not run for this report.",
    "checks_summary": (
        "{critical} critical, {warning} warning and {info} information findings; "
        "{passed} checks passed, {not_applicable} not applicable, {disabled} disabled."
    ),
    "checks_note": (
        "Thresholds come from the user's configuration file. A finding is a prompt to review "
        "the portfolio, not a recommendation to trade."
    ),
    "findings": "Findings",
    "severity": "Severity",
    "check": "Check",
    "subject": "Subject",
    "observed": "Observed",
    "threshold": "Threshold",
    "details": "Details",
    "severity_info": "Information",
    "severity_warning": "Warning",
    "severity_critical": "Critical",
    "subject_portfolio": "Portfolio",
    "checks_explained": "What the checks measure",
    "explanation": "Explanation",
    "checks_not_applicable": "Checks not applicable",
    "reason": "Reason",
    "reasons_in_english": "Reasons are given in English, as reported by the library.",
    "checks_disabled": "Disabled checks: {checks}.",
    "warn_critical_findings": "{count} critical health-check findings: see Health checks.",
}

_IT = {
    "report_title": "Report del portafoglio",
    "base_currency": "Valuta di base",
    "period": "Periodo",
    "generated_at": "Generato il",
    "as_of": "Dati aggiornati al",
    "warnings": "Avvisi",
    "summary": "Riepilogo",
    "end_value": "Valore finale",
    "net_flows": "Flussi esterni netti",
    "pnl": "Risultato",
    "twr": "Rendimento time-weighted (TWR)",
    "twr_definition": "Misura gli investimenti, neutralizzando versamenti e prelievi.",
    "twr_annualised": "TWR annualizzato",
    "mwr": "Rendimento money-weighted (MWR, XIRR, annuo)",
    "mwr_definition": "Misura l'esperienza dell'investitore, compresa la tempistica dei flussi.",
    "not_comparable": "TWR e MWR misurano cose diverse e non sono confrontabili.",
    "max_drawdown": "Drawdown massimo (percorso TWR)",
    "volatility": "Volatilità annualizzata",
    "volatility_omitted": (
        "Volatilità omessa: nessuna frequenza regolare dei rendimenti dichiarata."
    ),
    "risk_free_total": "Rendimento privo di rischio nel periodo ({source})",
    "sharpe": "Sharpe ratio (TWR in eccesso rispetto al tasso privo di rischio, annualizzato)",
    "sharpe_value": "{value} ± {se} (n = {n})",
    "sharpe_missing": "Lo Sharpe ratio non è mostrato: {reason}",
    "tax_title": "Posizione fiscale (analisi, non consulenza fiscale)",
    "tax_intro": "Conto in regime {regime}. Regole verificate al {checked}.",
    "tax_regime_amministrato": "amministrato (il broker trattiene le imposte)",
    "tax_regime_dichiarativo": "dichiarativo (le imposte le dichiari tu)",
    "tax_rules": (
        "I guadagni su ETF e fondi sono redditi di capitale, tassati per intero; le perdite su "
        "di essi e i risultati su azioni, obbligazioni ed ETC sono redditi diversi. Le minus "
        "compensano solo redditi diversi, dalle più vecchie, fino al 31 dicembre del quarto "
        "anno successivo. La quota dovuta ai titoli di Stato conta per il 48,08 %."
    ),
    "tax_estimate": (
        "In questo regime non si trattiene nulla: l'imposta mostrata è una stima da dichiarare."
    ),
    "tax_flagged": (
        "Non calcolato: {names}. I fondi domiciliati fuori da UE e SEE sono tassati con le "
        "aliquote progressive IRPEF."
    ),
    "tax_sources": "Fonti: {sources}.",
    "tax_events": "Vendite e imposte",
    "tax_events_note": (
        "Risultato: al netto delle commissioni, prima delle imposte. Base: dopo la quota dei "
        "titoli di Stato. Differenza: imposta trattenuta meno imposta dovuta; una differenza è "
        "mostrata, mai assorbita."
    ),
    "tax_category": "Categoria",
    "tax_cat_redditi_di_capitale": "Redditi di capitale",
    "tax_cat_redditi_diversi": "Redditi diversi",
    "tax_cat_not_computed": "Non calcolato",
    "tax_result": "Risultato",
    "tax_public_share": "Titoli di Stato",
    "tax_base": "Base",
    "tax_offset": "Minus usate",
    "tax_due": "Imposta dovuta",
    "tax_withheld": "Imposta trattenuta",
    "tax_difference": "Differenza",
    "tax_totals": "Totali",
    "tax_losses_remaining": "Minus ancora utilizzabili",
    "tax_losses": "Zainetto fiscale per anno",
    "tax_year": "Anno",
    "tax_amount": "Minus",
    "tax_used": "Usate",
    "tax_expired": "Scadute",
    "tax_remaining": "Residue",
    "tax_usable_until": "Utilizzabili fino al",
    # --- Svizzera (fase 9.2) --------------------------------------------------------------
    "ch_intro": (
        "Investitore privato residente in Svizzera. Regole verificate al {checked}. Le imposte "
        "sono stime alle aliquote che hai indicato, non una tassazione."
    ),
    "ch_gains_rule": (
        "Gli utili di capitale sulla sostanza privata non sono imponibili, salvo che "
        "l'investitore sia considerato un commerciante professionale di titoli."
    ),
    "ch_safe_haven_rule": (
        "I criteri della circolare AFC n. 36 sono verificati anno per anno. Se sono tutti e "
        "cinque rispettati, il commercio professionale è escluso; altrimenti non può essere "
        "escluso, e l'autorità fiscale valuta il caso nel suo insieme."
    ),
    "ch_first_year": (
        "{year}: il volume è confrontato con la prima valutazione del conto, perché non ce "
        "n'è una precedente."
    ),
    "ch_income_rule": (
        "Dividendi e interessi sono reddito per il loro importo lordo. Il reddito reinvestito "
        "di un fondo ad accumulazione è tassato ogni anno, alla chiusura dell'esercizio, "
        "secondo l'importo per quota del listino dei corsi che hai indicato."
    ),
    "ch_withholding_rule": (
        "L'imposta preventiva svizzera del 35 % sugli strumenti svizzeri è rimborsata se il "
        "reddito è dichiarato. Le imposte trattenute all'estero, o sugli interessi senza "
        "strumento, sono elencate ma non classificate."
    ),
    "ch_wealth_rule": (
        "La sostanza è il valore del conto all'ultima valutazione di ogni anno; i corsi di "
        "fine anno del listino AFC possono differire leggermente."
    ),
    "ch_settings": "Aliquote che hai indicato",
    "ch_marginal_rate": "Aliquota marginale sul reddito",
    "ch_wealth_tax_rate": "Aliquota dell'imposta sulla sostanza",
    "ch_years": "Posizione fiscale per anno",
    "ch_gains": "Utili realizzati",
    "ch_income": "Reddito imponibile",
    "ch_income_tax": "Imposta sul reddito (stima)",
    "ch_refundable": "Imposta preventiva rimborsabile",
    "ch_wealth": "Sostanza a fine anno",
    "ch_wealth_tax": "Imposta sulla sostanza (stima)",
    "ch_year_open": "anno non concluso",
    "ch_safe_haven": "Circolare 36",
    "ch_conclusion_met": "porto sicuro rispettato",
    "ch_conclusion_not_excluded": "commercio professionale non escluso",
    "ch_conclusion_incomplete": "incompleto (dati mancanti)",
    "ch_criterion": "Criterio",
    "ch_criterion_holding": "Durata di possesso dei titoli venduti, almeno 6 mesi",
    "ch_criterion_volume": "Acquisti e vendite, al massimo 5 volte il valore iniziale",
    "ch_criterion_gains": "Utili realizzati, sotto il 50 % del reddito netto",
    "ch_criterion_debt": "Nessun finanziamento con debiti",
    "ch_criterion_derivatives": "Derivati solo a copertura",
    "ch_limit": "Limite",
    "ch_detail": "Possesso più breve",
    "ch_result": "Esito",
    "ch_result_met": "rispettato",
    "ch_result_not_met": "non rispettato",
    "ch_result_not_checked": "non verificato (dato mancante)",
    "ch_safe_haven_note": (
        "Le durate di possesso seguono il primo entrato, primo uscito. Un conto finanziato con "
        "debiti richiede i tuoi interessi passivi, che qrlab non conosce."
    ),
    "ch_income_items": "Redditi",
    "ch_income_note": "Importi in CHF, convertiti a ogni data.",
    "ch_income_kind": "Tipo",
    "ch_income_dividend": "dividendo",
    "ch_income_interest": "interesse",
    "ch_income_reported_income": "reddito del fondo (listino)",
    "ch_cash": "liquidità",
    "ch_units": "Quote",
    "ch_per_unit": "Per quota",
    "ch_gross": "Lordo",
    # --- il modello configurabile (fase 9.3) --------------------------------------------
    "custom_title": (
        "Stima delle imposte: un modello semplificato che hai configurato, non la legge di un paese"
    ),
    "custom_intro": (
        "Modello: {description}. Le regole sono quelle che hai indicato; non si applica la "
        "legge di alcun paese. Le imposte sono stime."
    ),
    "custom_order": (
        "Per anno solare: il risultato di ogni vendita al costo medio; la parte esente per "
        "durata di possesso; le perdite; la franchigia; poi le aliquote."
    ),
    "custom_losses_netted": (
        "Le perdite si compensano con gli utili dell'anno; una perdita netta si può usare "
        "nei {years} anni successivi, dalla più vecchia."
    ),
    "custom_losses_ignored": "Le perdite sono ignorate: ogni utile è tassato da solo.",
    "custom_exempt": (
        "Gli utili sulle quote possedute da almeno {months} mesi sono esenti; le quote vendute "
        "seguono il primo entrato, primo uscito, un'approssimazione accanto al costo medio."
    ),
    "custom_no_exempt": "Nessun utile è esente per durata di possesso.",
    "custom_withheld": (
        "L'imposta trattenuta sui redditi è mostrata accanto all'imposta sui redditi, non "
        "scalata: se lo sia dipende dal paese e dal trattato."
    ),
    "custom_gains_rate": "Aliquota sugli utili",
    "custom_income_rate": "Aliquota sui redditi",
    "custom_wealth_tax_rate": "Aliquota sul patrimonio",
    "custom_allowance": "Franchigia annua sugli utili",
    "custom_settings": "Aliquote che hai indicato",
    "custom_amounts": "Importi che hai indicato",
    "custom_years": "Imposte per anno (stime)",
    "custom_years_note": "Le tue regole, applicate come indicato; non la legge di un paese.",
    "custom_result": "Risultato realizzato",
    "custom_exempt_amount": "Esente per possesso",
    "custom_taxable_gains": "Utili imponibili",
    "custom_taxable_losses": "Perdite imponibili",
    "custom_losses_used": "Perdite usate",
    "custom_allowance_used": "Franchigia usata",
    "custom_taxable": "Imponibile dopo perdite e franchigia",
    "custom_gains_tax": "Imposta sugli utili",
    "not_annualised": "Non annualizzato: il periodo è inferiore a un anno.",
    "positions": "Posizioni",
    "account": "Conto",
    "isin": "ISIN",
    "name": "Nome",
    "quantity": "Quantità",
    "price": "Prezzo",
    "price_date": "Data prezzo",
    "currency": "Valuta",
    "value": "Valore",
    "weight": "Peso",
    "cost_basis": "Costo",
    "unrealised": "Plus/minus non realizzata",
    "cash": "Liquidità",
    "local_amount": "Importo",
    "base_amount": "In valuta di base",
    "pnl_breakdown": "Scomposizione del risultato",
    "realised": "Realizzato",
    "unrealised_change": "Non realizzato (variazione)",
    "income": "Proventi (netti)",
    "costs": "Costi",
    "cash_fx": "Effetto cambio sulla liquidità",
    "transfers": "Plusvalenze portate da trasferimenti",
    "residual": "Residuo (deve essere zero)",
    "income_costs": "Proventi e costi",
    "date": "Data",
    "kind": "Tipo",
    "amount": "Importo",
    "figures": "Grafici",
    "figure_value": "Valore del portafoglio",
    "figure_twr": "TWR cumulato",
    "figure_drawdown": "Drawdown (percorso TWR)",
    "flows_marker": "Flussi esterni",
    "data_assumptions": "Dati e ipotesi",
    "sources": "Fonti dei dati",
    "source": "Fonte",
    "dataset": "Dataset",
    "retrieved": "Acquisito il",
    "sha256": "SHA-256",
    "terms": "Condizioni",
    "assumptions": "Ipotesi",
    "flow_timing": "Tempistica dei flussi",
    "cost_basis_method": "Costo fiscale",
    "cost_basis_value": "Costo medio ponderato, oneri di acquisto inclusi",
    "fx_source": "Conversione valutaria",
    "price_staleness": "Età massima dei prezzi (giorni)",
    "carried_forward": "Valori riportati da date precedenti",
    "requested_date": "Richiesta",
    "used_date": "Usata",
    "import_notes": "Note di importazione",
    "disclaimer": "Analisi, non consulenza finanziaria.",
    "private_reminder": "Questo report può contenere dati finanziari personali: tienilo privato.",
    "version": "Versione qrlab",
    "warn_stale_price": "Prezzo di {isin} per il {requested} preso dal {used}.",
    "warn_stale_fx": "Cambio {currency} per il {requested} preso dal {used}.",
    "warn_residual": "Il residuo del risultato è {value}, non zero: controlla i dati.",
    "warn_mwr_roots": "L'MWR non è unico: tassi candidati {rates}.",
    "warn_missing_master": "Nessuna anagrafica per {isin}: al posto del nome è mostrato l'ISIN.",
    "warn_skipped": "Nessun TWR per {dates}: capitale iniziale nullo.",
    "not_enough_dates": "Date di valorizzazione insufficienti per calcolare i rendimenti.",
    "none": "Nessuno",
    "not_available": "n.d.",
    "timing_start_of_day": "Inizio giornata",
    "timing_end_of_day": "Fine giornata",
    "holdings_count": "Posizioni in portafoglio",
    "kind_deposit": "Versamento",
    "kind_withdrawal": "Prelievo",
    "kind_buy": "Acquisto",
    "kind_sell": "Vendita",
    "kind_dividend": "Dividendo",
    "kind_interest": "Interessi",
    "kind_fee": "Commissione",
    "kind_tax": "Imposta",
    "kind_fx_conversion": "Cambio valuta",
    "kind_transfer_in": "Trasferimento in entrata",
    "kind_transfer_out": "Trasferimento in uscita",
    "kind_split": "Frazionamento",
    "projection": "Proiezione",
    "projection_not_computed": "Nessuna proiezione è stata calcolata per questo report.",
    "projection_note": (
        "Le proiezioni sono scenari generati dalle ipotesi qui sotto, non previsioni né "
        "consulenza. I risultati sono distribuzioni; ogni probabilità ha il suo errore Monte Carlo."
    ),
    "projection_costs_note": (
        "I costi dei fondi (TER) vanno nelle ipotesi di rendimento. Il modello fiscale non "
        "riporta le minusvalenze e usa un'aliquota unica: è un esempio, non consulenza fiscale."
    ),
    "engine": "Motore dei rendimenti",
    "paths": "Percorsi simulati",
    "horizon": "Orizzonte",
    "years": "{n} anni",
    "initial_wealth": "Capitale iniziale",
    "flows": "Flussi",
    "flow_contribution": "versamento {amount} nei periodi {first}-{last} ({indexed})",
    "flow_withdrawal": "prelievo netto {amount} nei periodi {first}-{last} ({indexed})",
    "indexed": "indicizzato all'inflazione",
    "fixed": "fisso",
    "timing_start_of_period": "Inizio di ogni periodo",
    "timing_end_of_period": "Fine di ogni periodo",
    "rebalancing": "Ribilanciamento",
    "rebalance_never": "Mai (compra e tieni)",
    "rebalance_every": "Ogni {n} periodi",
    "annual_cost": "Costi annui",
    "inflation": "Inflazione (annua)",
    "capital_gains_tax": "Imposta sulle plusvalenze",
    "wealth_tax": "Imposta patrimoniale (annua)",
    "terminal_wealth": "Patrimonio finale",
    "percentile": "Percentile",
    "real": "Reale (moneta di oggi)",
    "nominal": "Nominale",
    "after_tax": "Nominale dopo le imposte di liquidazione",
    "after_tax_note": "I valori al netto delle imposte assumono la vendita di tutto alla fine.",
    "probabilities": "Obiettivo, esaurimento e rischio di sequenza",
    "goal": "Probabilità di raggiungere {goal} (reale)",
    "depletion": "Probabilità di esaurire il capitale",
    "median_depletion": "Periodo mediano di esaurimento",
    "mean_terminal_real": "Patrimonio finale reale medio",
    "sequence_worst": "Patrimonio finale reale mediano, peggior 10 % dei primi {n} periodi",
    "sequence_best": "Patrimonio finale reale mediano, miglior 10 % dei primi {n} periodi",
    "se_note": "± indica un errore standard Monte Carlo.",
    "sensitivity": "Sensibilità alle ipotesi",
    "assumption": "Variazione",
    "goal_probability": "Probabilità dell'obiettivo",
    "median_real": "Patrimonio finale reale mediano",
    "sensitivity_note": "Ogni variazione usa gli stessi numeri casuali del caso base.",
    "sens_base": "Nessuna (caso base)",
    "sens_mean_down": "Rendimento medio -1 punto annuo",
    "sens_mean_up": "Rendimento medio +1 punto annuo",
    "sens_vol_down": "Volatilità x0,8",
    "sens_vol_up": "Volatilità x1,2",
    "sens_inflation_down": "Inflazione -1 punto",
    "sens_inflation_up": "Inflazione +1 punto",
    "sens_costs_up": "Costi +0,5 punti",
    "sens_costs_down": "Costi -0,5 punti",
    "fan_chart": "Patrimonio proiettato in moneta di oggi (percentili)",
    "risk_stress": "Rischio e stress test",
    "risk_not_computed": "Rischio e stress test non sono stati calcolati per questo report.",
    "risk_window": (
        "Le misure di rischio sono su un periodo ({frequency}), stimate su {n} rendimenti dal "
        "{start} al {end}; non sono annualizzate."
    ),
    "stress_note": (
        "Gli stress test sono analisi 'what if' sui pesi di oggi, non previsioni né "
        "probabilità. Le simulazioni via proxy usano i beta fattoriali e ignorano il rischio "
        "specifico."
    ),
    "risk_volatility": "Contributi alla volatilità",
    "holding": "Posizione",
    "contribution": "Contributo",
    "share": "Quota",
    "total": "Totale",
    "risk_var_es": "Value at risk ed expected shortfall al {confidence}",
    "method": "Metodo",
    "var_note": "I numeri positivi sono perdite. Nessun metodo è 'il' VaR: vanno confrontati.",
    "benchmark": "Benchmark",
    "benchmark_none": "Per questo report non è stato fornito un benchmark.",
    "benchmark_intro": (
        "Benchmark: {name}, una serie total return in {currency}, valutata in {base} con il "
        "cambio BCE di ogni data."
    ),
    "benchmark_no_period": "Non c'è alcun periodo fra due date di valutazione da confrontare.",
    "benchmark_window": (
        "Il confronto usa i {n} periodi fra date di valutazione dal {start} al {end}; un "
        "rendimento nella prima data di valutazione (da un versamento alla chiusura del "
        "giorno) è escluso."
    ),
    "benchmark_measures": "Portafoglio rispetto al benchmark",
    "benchmark_portfolio_total": "Rendimento del portafoglio in questi periodi",
    "benchmark_total": "Rendimento del benchmark in questi periodi",
    "benchmark_difference": "Differenza (punti percentuali)",
    "tracking_error": "Tracking error (annualizzato)",
    "information_ratio": "Information ratio (annualizzato)",
    "beta": "Beta",
    "beta_excess": "Beta (sugli extra-rendimenti rispetto al tasso privo di rischio)",
    "beta_plain": "Beta (sui rendimenti; nessuna serie priva di rischio fornita)",
    "alpha_annual": "Alpha (annualizzato)",
    "r_squared": "R quadro",
    "observations": "Osservazioni",
    "with_se": "{value} (errore standard {se})",
    "benchmark_missing": "{measure}: non disponibile ({reason}).",
    "benchmark_conventions": (
        "Rendimenti semplici. Rendimento attivo = rendimento del portafoglio - rendimento del "
        "benchmark, per periodo. Annualizzato da rendimenti mensili con 12 e radice di 12, "
        "il che presuppone assenza di autocorrelazione. Minimi quadrati ordinari con errori "
        "standard classici. Descrittivo: una finestra breve dice poco sull'abilità. Un "
        "benchmark di un altro universo o un indice di prezzo renderebbero questi numeri "
        "privi di senso."
    ),
    "benchmark_carried": "Benchmark: {what}",
    "return_sources": "Rendimenti usati per il rischio",
    "return_series": "Serie",
    "income_in_returns": "Proventi distribuiti",
    "income_included": "inclusi",
    "income_excluded": "esclusi",
    "return_sources_note": (
        "Il portafoglio è valutato ai prezzi di mercato. Il rischio e i controlli di "
        "diversificazione usano rendimenti che includono i proventi distribuiti solo per le "
        "serie indicate."
    ),
    "return_source_total_return_file": "Serie total return fornita",
    "return_source_distributions": "Prezzo più le distribuzioni fornite",
    "return_source_total_return_prices": "File di prezzi total return",
    "return_source_accumulating": "Prezzo di un fondo ad accumulazione",
    "return_source_no_income": "Prezzo di un ETC (nessun provento)",
    "return_source_distributing": "Prezzo di un fondo a distribuzione",
    "return_source_policy_unknown": "Prezzo (politica di distribuzione sconosciuta)",
    "return_source_stock": "Prezzo di un'azione",
    "return_source_bond": "Prezzo di un'obbligazione",
    "return_source_other": "Prezzo",
    "scenarios": "Scenari di stress",
    "scenario": "Scenario",
    "dates_used": "Date usate",
    "portfolio_return": "Rendimento del portafoglio",
    "not_covered": "Non coperto",
    "not_covered_note": (
        "Il peso non coperto è escluso dal dato di portafoglio, mai considerato senza perdite."
    ),
    "scenario_detail": "Scenari di stress per posizione",
    "base_return": "Rendimento in valuta di base",
    "scenario_historical": "Storico",
    "scenario_hypothetical": "Ipotetico",
    "method_direct": "Storia propria",
    "method_proxy": "Proxy fattoriale",
    "method_shock": "Shock diretto",
    "method_currency_only": "Solo cambio",
    "method_cash": "Liquidità",
    "method_not_covered": "Non coperto",
    "lookthrough": "Look-through",
    "lookthrough_not_done": (
        "Il look-through delle partecipazioni non è stato fatto per questo report."
    ),
    "lt_as_reported": (
        "Le partecipazioni dei fondi sono usate come pubblicate: il peso che non spiegano è "
        "mostrato a parte, mai ripartito sulle altre voci."
    ),
    "lt_normalised": "Le partecipazioni sono riscalate per sommare al 100 % (scelta esplicita).",
    "lt_buckets": (
        "Valori ignoti, fondi senza dati sulle partecipazioni e liquidità sono voci separate; "
        "non sono mai contati come un paese, un settore o un titolo."
    ),
    "lt_no_issuer_map": (
        "Nessuna mappa degli emittenti: la concentrazione è per titolo, non per emittente."
    ),
    "holdings_dates": "Date delle partecipazioni",
    "holdings_date": "Partecipazioni al",
    "age_days": "Età (giorni)",
    "lt_country": "Paese",
    "lt_sector": "Settore",
    "lt_currency": "Valuta (dopo la copertura)",
    "lt_security": "Titolo",
    "lt_more": "{count} voci minori non mostrate.",
    "lt_overlap": "Sovrapposizione tra fondi",
    "fund": "Fondo",
    "overlap": "Sovrapposizione",
    "overlap_by_name": "Di cui per nome",
    "lt_overlap_note": (
        "I titoli sono abbinati per ISIN e, dove un fondo ne indica uno senza ISIN, per nome "
        "normalizzato. Gli abbinamenti per nome sono approssimati."
    ),
    "unmatched": "Senza ISIN",
    "lt_tracking": "Tracking difference",
    "series_type": "Serie",
    "series_nav": "NAV",
    "series_total_return": "Total return",
    "series_price": "Prezzo",
    "td_period": "Nel periodo",
    "td_annualised": "Annualizzata",
    "ter": "TER",
    "td_plus_ter": "TD + TER",
    "td_note": (
        "Rendimento del fondo meno rendimento dell'indice. Non annualizzata su meno di un anno. "
        "TD + TER sotto zero indica costi oltre il TER."
    ),
    "bucket_unknown": "Sconosciuto",
    "bucket_unexplained": "Non spiegato dalle partecipazioni",
    "bucket_not_looked_through": "Fondi senza dati sulle partecipazioni",
    "health_checks": "Controlli di salute",
    "checks_not_run": "I controlli di salute non sono stati eseguiti per questo report.",
    "checks_summary": (
        "{critical} segnalazioni critiche, {warning} avvisi e {info} informative; "
        "{passed} controlli superati, {not_applicable} non applicabili, {disabled} disattivati."
    ),
    "checks_note": (
        "Le soglie vengono dal file di configurazione dell'utente. Una segnalazione invita a "
        "rivedere il portafoglio, non è una raccomandazione di operare."
    ),
    "findings": "Segnalazioni",
    "severity": "Gravità",
    "check": "Controllo",
    "subject": "Oggetto",
    "observed": "Valore osservato",
    "threshold": "Soglia",
    "details": "Dettagli",
    "severity_info": "Informativa",
    "severity_warning": "Avviso",
    "severity_critical": "Critica",
    "subject_portfolio": "Portafoglio",
    "checks_explained": "Cosa misurano i controlli",
    "explanation": "Spiegazione",
    "checks_not_applicable": "Controlli non applicabili",
    "reason": "Motivo",
    "reasons_in_english": "I motivi sono in inglese, come riportati dalla libreria.",
    "checks_disabled": "Controlli disattivati: {checks}.",
    "warn_critical_findings": (
        "{count} segnalazioni critiche nei controlli di salute: vedi la sezione."
    ),
}

LABELS: Mapping[Language, Mapping[str, str]] = MappingProxyType(
    {Language.EN: MappingProxyType(_EN), Language.IT: MappingProxyType(_IT)}
)
"""Labels per language."""


def label(key: str, language: Language, **values: str) -> str:
    """Return the label ``key`` in ``language``, with ``{placeholders}`` filled in."""
    text = LABELS[language][key]
    return text.format(**values) if values else text
