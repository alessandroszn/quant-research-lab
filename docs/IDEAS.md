# Ideas

Out-of-scope ideas, triaged at each milestone. Nothing here is planned until it moves into
`ROADMAP.md`.

| Idea | Raised in | Notes |
|---|---|---|
| Exchange calendars (NYSE, Xetra, Borsa Italiana, LSE) | 1.1 `core` | Needs a reliable source of exchange holidays and early closes; until then, `BusinessCalendar` with user-supplied holidays covers them. |
| Pre-2002 TARGET closing days | 1.1 `core` | 1999–2001 had extra closing days (e.g. 31 December); only needed for euro data before 2002. |
| Complete ISO 4217 table | 1.1 `core` | `MINOR_UNITS` lists 36 common currencies; extend from the official ISO list when a portfolio needs others. |
| FRED as a data source | 1.2 `data` | Excluded: its terms prohibit storing or caching data without written consent. Reconsider only with written permission or a no-cache design. |
| Ken French portfolio files | 1.2 `data` | 25/100 size–value portfolios, industry portfolios; multi-table files. Add when a study (5.3) needs them. |
| Retry with back-off for downloads | 1.2 `data` | The ECB Data Portal intermittently returns HTTP 504; today a failed download raises and nothing is stored. |
| Issuer holdings adapters (iShares, Xtrackers, Vanguard, Amundi, SPDR, Invesco) | 1.3 `instruments` | Each needs its own terms-of-use review before any download code. |
| Exchange listings and trading currencies | 1.3 `instruments` | Needed when valuing transactions on a specific exchange (2.1). |
| FIFO and specific-lot cost basis | 2.1 `portfolio` | Average cost (Italian regime amministrato) is implemented; other methods for other tax regimes. |
| Original purchase FX rate on transfers in | 8.8 | A foreign fund's original cost is converted at the transfer date's rate; the rates of the original purchases would give the exact euro cost. |
| Publish on PyPI | 10.3 | 1.0.0 went out on GitHub only: the owner has no PyPI account yet. With the accounts, add the trusted publishers (`releasing.md`, step 4) and release the next version to PyPI. |
| Hashes of the wheel and sdist in `SHA256SUMS.txt` | 10.3 | The file lists only the two Windows files, with Windows line endings, so `sha256sum -c` fails on Linux. GitHub shows a SHA-256 for every release file; the wheel is now the install path, so the file should cover it too. |
| Distributions from the issuers' files | 11.1 | The owner types the distributions or gives a total-return file. Reading them from issuer files needs each source's terms checked first. |
| Base-currency returns in the diversification checks | 11.1 | They use each position's local-currency returns, while the risk section converts to the base currency. Which one the checks should measure is its own question. |
| A composite or per-asset-class benchmark | 11.2 | The report takes one total-return series. A weighted benchmark needs its weights, rebalancing rule and dates stated. |
| The `risk.beta` check on excess returns | 8.5, 11.2 | The check regresses plain returns (2.4); the report's section uses excess returns over the €STR when given. The checks have no risk-free series. |
| The partial first day in the return checks | 11.2 | With `flow_timing = "start"` the TWR has a return on the first date, from a deposit to that day's close. The benchmark comparison leaves it out; the volatility, drawdown and other return checks still include it when there is no benchmark. |
| Up and down capture in the report | 11.2 | `qrlab.metrics.up_capture` and `down_capture` exist; they would join the benchmark section. |
| Italian stamp duty and IVAFE on cash | 11.3 | The fixed €34.20 on current accounts and savings books (Italy and abroad) depends on average balances by account, which the ledger does not hold. |
| The foreign wealth-tax credit in the IVAFE | 11.3 | A wealth tax paid abroad on the same products is deducted up to the IVAFE; it needs a per-year input. |
| Stamp duty and IVAFE from 2027 | 11.3 | The testo unico D.Lgs. 123/2025 applies from 1 January 2027 (D.L. 200/2025); its articles must be checked before those years are computed. |
| The Agenzia's monthly average rates for the IVAFE | 11.3 | The return converts foreign values at the provvedimento's monthly averages; the report uses the ECB rate of the day. |
| Betas estimated for the stress-test proxies | 11.4 | The report takes the owner's betas. Estimating them from the overlap of a position's returns and the factors, with standard errors and R², is a modelling choice of its own. |
| Proxies to extend the VaR backtest history | 11.4 | The backtest uses the common history of the held positions; proxied returns could reach further back, with the proxy's understatement of own risk. |
| Expected-shortfall backtests | 11.4 | For example Acerbi–Székely; the report backtests the VaR only. |
| Undefined Cornish-Fisher forecasts in a VaR backtest | 11.4 | A window whose expansion is not a quantile stops the run (as in `risk_report`); the forecast could instead be skipped and counted. |
| Percentage contribution linking (Carino, GRAP) | 2.1 `portfolio` | Planned with attribution (4.4); money contribution by position exists. |
| Automatic block length (Politis-White 2004) | 2.2 `stats` | The stationary bootstrap takes an explicit mean block length today. |
| Severity per finding in the app | 2.4 `checks` | Let the user acknowledge or snooze a finding; needs persistent state (phase 6). |
| Reconciliation with a broker export | 8.1, 8.8 | The old 8.1: run the report on a broker export and reconcile value, cash and realised gains with the broker's statements, once such an export exists. |
| Price fetcher for a licensed API | 8.8 | Automatic fund prices from an API with the user's own key, with its terms recorded; no free source with clear terms was found. |
| Germany in detail (the old 9.4) | 9 | Abgeltungsteuer with the solidarity surcharge (church tax optional); Teilfreistellung by fund type (a new instrument field); the yearly Vorabpauschale with each year's base rate; the Sparer-Pauschbetrag and the two loss pots; FIFO cost basis next to average cost. 20–30 h. The configurable model (9.3) is the first view meanwhile. |
| Swiss treaty relief and more | 9.2 | Relief for foreign withholding tax (DA-1) and the US additional withholding; real-estate funds (LIFD art. 20 cpv. 1 lett. e); pillar 3a; reports in German and French; reading the ESTV price list (ICTax) automatically, after its terms are checked. |
| Italian taxes on income | 8.6 | Recompute dividend and coupon taxes (with foreign withholding and treaties); foreign currency as redditi diversi. Stamp duty and IVAFE are phase 11.3. |
| Currency model in projections | 8.4 | Foreign assets and cash are projected in the base currency; their stated return and volatility must include the currency risk. |
| Duplicated exposure by name | 8.2 | `duplicated_exposure` matches securities by ISIN only; files without ISINs (some issuers) could use the normalised names already used for overlap, labelled approximate. |
| Fund-of-funds look-through | 2.5 `lookthrough` | A fund held inside a fund is one security; a second level needs that fund's holdings. |
| Sector for direct positions | 2.5 `lookthrough` | Master data has no sector field, so direct stocks show an unknown sector. |
| Constant-correlation shrinkage target | 3.1 `risk` | Ledoit-Wolf (2004, JPM) target; only the scaled identity is implemented. |
| Minimum-torsion effective bets | 3.1 `risk` | Meucci et al. (2015) remove the dependence of ENB on the principal-component rotation. |
| GARCH volatility filter | 3.1 `risk` | Filtered historical simulation uses EWMA; GARCH needs maximum-likelihood estimation and diagnostics. |
| Basel traffic-light zones | 3.1 `risk` | Green/yellow/red classification of 250-day VaR backtests. |
| Duration-based rate shocks | 3.2 `scenarios` | Needs a duration (and convexity) field in master data for bond funds. |
| Residual risk in proxy replays | 3.2 `scenarios` | Proxy replays ignore specific risk; a band from the residual variance would show the uncertainty. |
| Stress-period betas | 3.2 `scenarios` | Betas estimated in calm periods understate crisis co-movement; estimate them on stress windows too. |
| Regime-switching engine | 3.3 `simulation` | Optional in the roadmap; needs a Markov-switching estimation with diagnostics. |
| Stochastic inflation | 3.3 `simulation` | Inflation is a fixed annual rate; a joint model with returns (e.g. from HICP) would widen real outcomes. |
| Sensitivity for the bootstrap engine | 3.3 `simulation` | Shifting the mean and scaling volatility of resampled history needs a stated transformation. |
| Combinatorial purged cross-validation | 4.1 `validation` | Trains on data after the test window, which breaks the train-before-test rule; only with an explicit opt-in and a documented reason. |
| Robust or resampled mean-variance | 4.2 `optimization` | Michaud resampling or robust optimisation to tame estimation error in expected returns. |
| Optimisation report section | 4.2 `optimization` | Weights, contributions and out-of-sample comparisons in the HTML report, through the experiment runner. |
| Assets entering and leaving the universe | 4.3 `backtest` | Returns must be complete today; survivorship-free universes need assets with start and end dates. |
| Market impact and spreads | 4.3 `backtest` | Costs are proportional plus fixed; size-dependent impact matters for large trades. |
| Karnosky-Singer currency attribution | 4.4 `attribution` | Forward premia and hedging costs need interest rates per currency. |
| Multi-period currency attribution | 4.4 `attribution` | Currency effects are one period; linking them needs a stated convention. |
| Other linking methods (Menchero, Frongello) | 4.4 `attribution` | Carino is one convention; others give different splits of the same total. |
| `qrlab fetch` | 5.2 `experiments` | An explicit download step into the raw store (Ken French, ECB), kept separate from runs. |
| Trading costs of anomalies | 5.3 study 3 | Chen and Velikov (2023) estimate effective spreads; net-of-cost survival of the factor zoo needs their cost data. |
| Return kind carried by the data | 6.3b methodology | Metrics assume simple returns by contract; a series that carries its `ReturnKind` would catch log returns passed by mistake. |
| Code signing of the Windows build | 6.2 build | Removes the SmartScreen warning; needs a paid certificate or Azure Trusted Signing. |
| macOS build | 6.2 build | A PyInstaller `.app` and a disk image, built on a macOS runner with the same source-versus-frozen check. |
| Rebalancing with contributions | 5.3 study 4 | Monthly savings can rebalance without selling (cash-flow rebalancing), which avoids realising gains under Italian tax. |
| Hedged equity and loss carry-forward in study 4 | 5.3 study 4 | EUR-hedged equity (needs USD and EUR short rates) and the four-year carry-forward of capital losses (the engine has it since 8.6b, as `LossRules`). |
