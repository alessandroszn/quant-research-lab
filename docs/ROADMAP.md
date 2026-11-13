# Roadmap — Quant Research Lab

## How to read this roadmap

There are **no calendar dates**. The project can start in any month and move at any pace.
Phases are ordered by **dependency**: each one only uses what earlier phases built. Every phase
has an indicative effort in **focused hours** (working with Claude Code, including your review)
and a definition of done. Milestones are defined by **capability**, not by time.

Indicative total: **600–850 focused hours**. This is an estimate with wide uncertainty, not a
commitment; it is revised at each milestone.

## Vision

One coherent platform with three pillars, all built on the same tested library (`qrlab`):

1. **Portfolio & ETF analytics** — import a real portfolio (transactions, positions, cash in
   several currencies) and get a complete, explainable X-ray:
   - correct performance (time-weighted and money-weighted);
   - risk, factor exposures, and look-through exposures to countries, sectors and currencies;
   - ETF overlap, costs and tracking quality;
   - a configurable **health-check engine** of dozens of controls;
   - stress tests;
   - Monte Carlo **projections** for goals, savings plans and withdrawals.
2. **Research lab** — empirical asset pricing and strategy research: a backtest engine that makes
   look-ahead bias structurally hard, portfolio optimisation, time-aware validation,
   multiple-testing-aware inference, and four reproducible studies on public data.
3. **Desktop application** — a Windows `.exe` (PySide6) that puts both pillars behind a clean
   interface. Every analysis run from the app saves its configuration and can be reproduced
   from the command line.

"Huge" is only worth something if every part is **correct and verified**. Breadth is added layer
by layer, and no layer starts before the one below it is tested and reviewed.

## Decisions

| Topic | Decision |
|---|---|
| Product | Library + command-line interface + Windows desktop app (`.exe`) |
| Scope | Portfolio & ETF analytics + research lab + app, as below |
| Visibility | Private GitHub repository until the first milestone with a complete, verified deliverable (proposed: M2); then public |
| Development | Claude Code on the local Windows PC; rules in `CLAUDE.md` |
| Base currency | Configurable; EUR by default |
| Personal data | Real portfolios live only in the git-ignored `data/` folder; never committed or published |
| Positioning | Analytics and research tooling, not investment advice; reports say so |

## Overview

| Level | Phases | Milestone | Indicative hours |
|---|---|---|---|
| 0 | Setup | — | 4–6 |
| 1 Foundations | core, data, instruments, metrics | **M1 Analytics core** | 70–100 |
| 2 Portfolio | accounting & performance, stats, reporting v1, checks, look-through & ETF analysis | **M2 Portfolio X-ray** | 130–180 |
| 3 Risk & projections | risk models, scenarios, simulation & planning | **M3 Risk & Planning** | 80–110 |
| 4 Construction & backtest | validation, optimisation, backtest, attribution | **M4 Construction & Backtest** | 100–130 |
| 5 Research | inference, experiments/CLI, four studies | **M5 Research** | 120–170 |
| 6 Product | desktop app, `.exe` and installer, docs, release | **M6 v1.0** | 110–150 |

Releases: each phase ends with a SemVer minor release (`v0.N.0`). v1.0 is reached at M6.

---

## Level 0 — Setup (4–6 h)

- Move the verified skeleton to the Windows PC, run `uv sync` and the full quality gate.
- Private GitHub repo, first commit, CI green on Linux and Windows, `CHANGELOG.md`, tag v0.1.0.
- **Done when:** gate passes locally and in CI.

## Level 1 — Foundations → M1 Analytics core

### 1.1 `core` (12–18 h)
- Validated time series: sorted, unique `DatetimeIndex`; explicit NaN policy.
- Frequencies with explicit periods per year; business-day calendars.
- Returns: simple ↔ log, price → returns, excess returns, compounding, aggregation across
  frequencies.
- **Currency-aware amounts:** every monetary value carries its currency. Mixing currencies
  without an explicit, dated FX conversion raises an error.
- **Tests:** hand-calculated examples; round-trips; misalignment and currency-mixing raise.

### 1.2 `data` (20–30 h)
- A provider interface, so analytics never depend on where data comes from.
- Raw downloads stored unchanged, with provenance: source, URL, date, SHA-256 hash and range.
- Local cache; schema and unit validation.
- **Sources:**
  - Ken French Data Library (factors; portfolio files are added when a study needs them).
  - ECB reference FX rates.
  - ECB Data Portal: €STR (euro risk-free rate) and euro-area HICP (inflation). *FRED was
    dropped after the terms-of-use review: its terms prohibit storing or caching its data.*
  - **User CSV import** for prices, with an explicit mapping layer (formats never guessed).
    *Broker transaction import moved to 2.1, where the transaction schema is defined.*
  - ETF prices: the free source is chosen after reviewing its terms of use. User-supplied CSV is
    always supported.
- **Tests:** small committed fixture files; no network in tests.

### 1.3 `instruments` (12–18 h)
- Master data for ETFs and other assets:
  - ISIN, currency, domicile, replication method, distribution policy (accumulating or
    distributing), TER, benchmark index, asset class.
- Holdings snapshots with an **as-of date**, used later for look-through analysis.
- **Tests:** validation of ISIN check digits; missing or stale fields reported explicitly.

### 1.4 `metrics` (25–35 h)
- **Performance:**
  - arithmetic and geometric annualised return, volatility;
  - Sharpe ratio with the Lo (2002) standard error, Sortino;
  - drawdowns (depth, duration, recovery), Calmar, Ulcer index.
- **Risk:**
  - historical and parametric VaR/ES, skewness and kurtosis;
  - downside deviation, hit rate, gain/loss ratio.
- **Relative to a benchmark:**
  - tracking error, information ratio, beta and alpha;
  - up/down capture, active share (once holdings are available).
- **Tests:** hand-calculated series; analytical normal cases; simulation coverage of standard
  errors.

*Status: implemented and verified locally on 2026-11-10; pending CI on GitHub and your review.*

**M1 — Analytics core:** any return series, in any currency, can be loaded with provenance and
fully analysed with verified metrics.

## Level 2 — Portfolio → M2 Portfolio X-ray

### 2.1 `portfolio`: accounting & performance (25–35 h)
*Status: implemented and verified locally on 2026-11-10; pending CI and review.*
- **Broker transaction import** (moved from 1.2): broker exports mapped to the transaction
  schema, reusing the explicit CSV mapping layer of `data`.
- **Accounting:** transactions (buy, sell, dividend, fee, tax, deposit, withdrawal, FX), from
  which positions and cash are derived; multi-currency valuation in the base currency.
- **Performance:**
  - time-weighted return (TWR), measuring the investments;
  - money-weighted return (IRR/XIRR), measuring the investor's experience;
  - contribution by position;
  - the share of return coming from currency.
- **Tests:** a hand-reconciled toy portfolio (every number checked by hand); TWR equals simple
  return when there are no flows; XIRR agrees with closed-form cases.

### 2.2 `stats` (20–25 h)
*Status: implemented and verified locally on 2026-11-10; pending CI and review.*
- OLS with Newey–West standard errors (wrapping statsmodels); rolling regressions.
- Factor exposures (CAPM, FF3, FF5, momentum); stationary block bootstrap for confidence
  intervals.
- **Tests:** agreement with statsmodels; known-answer simulations.

### 2.3 `reporting` v1 (15–20 h)
*Status: implemented and verified locally on 2026-11-10; pending CI and review.*
- Tables and figures (Matplotlib, Agg backend) and a portfolio report in HTML.
- Every report states its data as-of dates, its assumptions and a "not investment advice" note.

### 2.4 `checks`: portfolio health-check engine (30–40 h)
- **A rule framework.** Each check has:
  - an identifier and a category;
  - a configurable threshold;
  - a severity (info / warning / critical);
  - a plain-language explanation;
  - the numbers that triggered it.
- **Initial checks, about 30**, grouped by category:
  - *Concentration:* largest position, top-5 weight, Herfindahl index, single issuer, single
    country, single sector, single currency.
  - *Diversification:* average correlation, diversification ratio, effective number of bets.
  - *Risk:* volatility vs. target, drawdown vs. tolerance, VaR/ES, beta, tail risk.
  - *Costs:* weighted TER, estimated total cost of ownership, trading-cost drag.
  - *ETF quality:* tracking difference and tracking error, fund size, replication method,
    domicile, distribution policy vs. stated preference.
  - *Overlap:* holdings overlap between ETFs; redundant funds.
  - *Currency:* unhedged foreign-currency exposure vs. base currency.
  - *Drift:* deviation from target weights; rebalancing needed.
  - *Data quality:* stale prices, stale holdings, missing data.
- **Tests:** for every check, a constructed portfolio that must trigger it and one that must not.
- *Split (design notes 2.4 and 2.5):* 27 checks use data that exists after 2.3. The 9 that
  need look-through are added in 2.5: country, sector and issuer concentration, fund overlap,
  duplicated exposure, tracking difference, tracking error, TD vs. TER, and stale holdings.
  The effective number of bets needs the risk models of 3.1.

### 2.5 Look-through & ETF analysis (25–35 h)
- Aggregated exposures through ETF holdings by country, sector, currency and issuer, with
  holdings as-of dates shown.
- Pairwise and portfolio-level ETF overlap.
- Tracking difference (ETF return minus index return, net of costs) and tracking error.
- Cost analysis: TER vs. realised tracking difference.
- **Tests:** synthetic ETFs with known holdings; overlap of identical funds is 100%.
- Adds the 9 look-through and tracking health checks (36 in total) and a look-through
  section in the portfolio report (design note 2.5).

**M2 — Portfolio X-ray:** import a real portfolio and get a complete, verified report of
performance, risk, exposures, ETF analysis and health checks. *Proposed moment to make the repo
public.*

## Level 3 — Risk & projections → M3 Risk & Planning

### 3.1 `risk` models (30–40 h)
- **Covariance estimators:** sample, EWMA, Ledoit–Wolf shrinkage.
- **Risk decomposition:** marginal and component contribution to volatility and ES; a factor
  risk model.
- **VaR/ES methods:** historical, parametric, Cornish–Fisher, filtered historical simulation.
- **VaR backtesting:** Kupiec and Christoffersen tests.
- **Tests:** component contributions sum to the total; analytical normal cases; VaR backtests
  on simulated data with a known exceedance rate.

### 3.2 `scenarios`: stress tests (20–30 h)
- Historical replays (e.g. 2008 crisis, 2020 Covid crash, 2022 rate shock) on the current
  portfolio.
- Hypothetical shocks to markets, factors, rates and FX, mapped to positions through
  estimated sensitivities.
- **Tests:** the shock of a single asset reproduces its weight times the shock; consistency
  between historical and mapped shocks.

### 3.3 `simulation`: projections & planning (30–40 h)
- **Monte Carlo engines:** parametric (normal, Student-t), block bootstrap of history,
  optionally regime-switching.
- **Planning:**
  - savings plans (PAC), lump sums, withdrawals;
  - inflation, fees, and a configurable tax model (e.g. Italian capital-gains rules,
    documented);
  - rebalancing during the projection.
- **Outputs:**
  - distributions, never single numbers: fan charts and percentiles;
  - probability of reaching a goal; sequence-of-returns risk;
  - sensitivity to assumptions.
- **Tests:** the expected value of the parametric engine matches the closed form; Monte Carlo
  error shrinks as 1/√N; seeded and reproducible.

**M3 — Risk & Planning:** the portfolio can be stress-tested and projected forward, with every
assumption visible and every risk number verified.

## Level 4 — Construction & backtest → M4

### 4.1 `validation` (15–20 h)
- Expanding and rolling walk-forward splits; purged and embargoed splits.
- **Tests:** the property *train strictly before test* is checked.

### 4.2 `optimization` (35–45 h)
- **Portfolio construction methods:**
  - 1/N, minimum variance, mean-variance with constraints;
  - risk parity / equal risk contribution, maximum diversification;
  - Black–Litterman, Hierarchical Risk Parity (López de Prado, 2016).
- **Constraints:** long-only, bounds, groups, turnover.
- **Rebalancing policies:** calendar vs. threshold, with costs and taxes.
- SciPy solvers first; `cvxpy` only if the constraints require it, as a documented decision.
- **Tests:** analytical two-asset solutions; constraint satisfaction; equal risk contributions
  verified.

### 4.3 `backtest` engine (30–40 h)
- Signals → target weights → realised weights → returns. `execution_lag ≥ 1` is required.
- Proportional and fixed costs; weight drift between rebalances; cash; time-series and
  cross-sectional strategies.
- Gross and net results are always reported together.
- **Leak test:** a deliberately leaked signal must give a different result, and the default
  API must refuse it.
- **Tests:** hand-checked P&L on a 3-asset toy example.

### 4.4 `attribution` (20–25 h)
- Brinson–Fachler (allocation, selection, interaction), factor-based attribution, currency
  attribution.
- **Tests:** effects sum to the active return; textbook examples.

**M4 — Construction & Backtest:** portfolios can be built, rebalanced and backtested without
look-ahead, and their results attributed.

## Level 5 — Research → M5

### 5.1 Inference (15–20 h)
- Holm and Benjamini–Hochberg corrections; probabilistic and deflated Sharpe ratio (Bailey &
  López de Prado, 2014); tests of Sharpe-ratio differences; bootstrap confidence intervals.

### 5.2 `experiments` runner + CLI (15–20 h)
- Every analysis or study is a TOML config. `qrlab run <config>` loads data, runs it, and writes
  a record: hypothesis, data and hashes, parameters, number of configurations tried, in-sample
  vs. out-of-sample, code version.
- This is the single entry point used by scripts, the CLI and the desktop app.

### 5.3 Studies (each 25–40 h, reproducible with one command, with a written report)
1. **Volatility-managed portfolios.** Moreira & Muir (2017, *JF*) vs. the critique of
   Cederburg, O'Doherty, Wang & Yan (2020, *JFE*): replicate, then evaluate out of sample and
   after costs.
2. **1/N vs. optimisation.** DeMiguel, Garlappi & Uppal (2009, *RFS*), extended with shrinkage,
   risk parity, Black–Litterman and HRP.
3. **The factor zoo.** Harvey, Liu & Zhu (2016, *RFS*), McLean & Pontiff (2016, *JF*), using
   Open Source Asset Pricing data (Chen & Zimmermann; terms checked first).
4. **Rebalancing for a EUR ETF investor.** Calendar vs. threshold rebalancing after costs, taxes
   and currency effects, using the platform's own portfolio, optimisation and simulation modules.

An honest null result is a valid result and is reported as such.

**M5 — Research:** four reproducible studies with reports.

## Level 6 — Product → M6 v1.0

### 6.1 Desktop app `qrlab_app` (60–80 h)
- PySide6. A thin layer over the experiments runner; **no financial logic in the GUI**.
- Long runs execute in worker threads.
- **Screens:**
  - Portfolio: import, X-ray, health checks.
  - Risk.
  - Scenarios.
  - Projections.
  - Optimiser.
  - Backtests & studies.
  - Data: sources, provenance, freshness.
  - History of runs.
- **Tests:** view-model logic unit-tested; off-screen smoke test in CI.

### 6.2 Windows `.exe` and installer (15–25 h)
- PyInstaller one-folder build, produced by a Windows job in GitHub Actions; installer on top
  (e.g. Inno Setup).
- The built executable runs a sample analysis end-to-end in CI.
- Known limits: large bundle size; a SmartScreen warning without code signing. Qt (LGPL)
  licence notices are shipped.

### 6.3 Docs, release and launch (30–40 h)
- API freeze; docs site (MkDocs Material) with guides, API reference, one methodology page per
  risk in the risk register, and the studies.
- PyPI release; Zenodo DOI; a combined working paper of the studies.
- Launch: README with figures, a post on alessandrozanichelli.com. (No LinkedIn post: decided by the owner on 2026-11-13.)

**M6 — v1.0.**

---

## Working method for each phase

1. **Design note:** inputs, outputs, edge cases, risks, test plan with hand-calculated
   examples. Reviewed before any code.
2. **Tests first** for financial formulas.
3. **Implement** in small PRs on feature branches; the quality gate must pass.
4. **Review** the diff, update `CHANGELOG.md`, tag the release.

## Risks to the plan

| Risk | Mitigation |
|---|---|
| Breadth without depth | No phase starts before the one below is tested and reviewed; each milestone is a usable, verified deliverable |
| Scope creep | Each phase has a fixed list; new ideas go in `docs/IDEAS.md` and are triaged at milestones |
| Data licences and availability (especially ETF prices and holdings) | Provider interface; user CSV import always works; terms of use reviewed before any source is added; data never committed |
| Projections taken as promises | Distributions only, assumptions shown, sensitivity analysis, explicit disclaimer |
| The app absorbs research time | The app starts after M5 and contains no financial logic |
| Personal financial data leaks | Data folder git-ignored; no real data in tests, fixtures, screenshots or reports that get published |

## Out of scope until v1.0

Live trading or broker APIs, intraday or tick data, machine-learning return forecasts, web
dashboards, macOS/Linux app builds, paid data (CRSP/Compustat), personalised investment advice.
