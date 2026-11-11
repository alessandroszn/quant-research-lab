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
| Country name to ISO code table | 1.3 `instruments` | Issuer holdings files use country names ("United States"); needed for look-through in 2.5. |
| Issuer holdings adapters (iShares, Xtrackers, Vanguard, Amundi, SPDR, Invesco) | 1.3 `instruments` | Each needs its own terms-of-use review before any download code. |
| Exchange listings and trading currencies | 1.3 `instruments` | Needed when valuing transactions on a specific exchange (2.1). |
| FIFO and specific-lot cost basis | 2.1 `portfolio` | Average cost (Italian regime amministrato) is implemented; other methods for other tax regimes. |
| Original cost on transfers in | 2.1 `portfolio` | Transfers in take market value as cost basis; carrying the original cost from another broker matters for taxes. |
| Percentage contribution linking (Carino, GRAP) | 2.1 `portfolio` | Planned with attribution (4.4); money contribution by position exists. |
| Automatic block length (Politis-White 2004) | 2.2 `stats` | The stationary bootstrap takes an explicit mean block length today. |
| International daily factors | 2.2 `stats` | French publishes daily Developed and Europe factors; only monthly and annual are parsed. |
| Fama-MacBeth regressions | 2.2 `stats` | Cross-sectional asset pricing tests, needed for the factor-zoo study (5.3). |
| Sharpe ratio in the portfolio report | 2.3 `reporting` | Needs a risk-free series (e.g. euro short-term rate) as a report input. |
| Translate library messages in reports | 2.3 `reporting` | Import notes and some error texts are English inside Italian reports. |
| PDF export of reports | 2.3 `reporting` | Roadmap mentions HTML/PDF; HTML only in v1. |
| Translate not-applicable reasons | 2.4 `checks` | Reasons are English library texts inside Italian reports, like import notes. |
| Beta on excess returns | 2.4 `checks` | Needs a risk-free series in `CheckContext`; with a constant rate the beta is the same. |
| Total-return position returns | 2.4 `checks` | Diversification checks use price returns; distributing funds look more volatile and less correlated than they are. |
| Severity per finding in the app | 2.4 `checks` | Let the user acknowledge or snooze a finding; needs persistent state (phase 6). |
| Issuer map loader (TOML) | 2.5 `lookthrough` | `look_through` takes a Python mapping today; a declared file would make it reusable. |
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
| Loss carry-forward in the tax model | 3.3 `simulation` | Italian capital losses can offset gains for four years; v1 does not carry them, which overstates taxes. |
| Sensitivity for the bootstrap engine | 3.3 `simulation` | Shifting the mean and scaling volatility of resampled history needs a stated transformation. |
| Combinatorial purged cross-validation | 4.1 `validation` | Trains on data after the test window, which breaks the train-before-test rule; only with an explicit opt-in and a documented reason. |
| Robust or resampled mean-variance | 4.2 `optimization` | Michaud resampling or robust optimisation to tame estimation error in expected returns. |
| Optimisation report section | 4.2 `optimization` | Weights, contributions and out-of-sample comparisons in the HTML report, through the experiment runner. |
| Assets entering and leaving the universe | 4.3 `backtest` | Returns must be complete today; survivorship-free universes need assets with start and end dates. |
| Market impact and spreads | 4.3 `backtest` | Costs are proportional plus fixed; size-dependent impact matters for large trades. |
