# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Study 2 (phase 5.3), 1/N against optimised portfolios (DeMiguel, Garlappi and Uppal 2009),
  extended with Ledoit-Wolf shrinkage, risk parity, HRP and Black-Litterman:
  - `qrlab.studies.one_over_n`:
    - rolling-window targets for eight long-only strategies;
    - execution through the backtest engine on daily returns, one trading day after each
      month-end decision;
    - net excess returns, Sharpe ratio, CEQ, turnover and drawdown;
    - Ledoit-Wolf HAC and Jobson-Korkie-Memmel tests against 1/N, with bootstrap intervals of
      the Sharpe and CEQ differences;
    - Holm and BH corrections, the deflated Sharpe ratio and an HTML report;
  - experiment kind `study_one_over_n` (tested end to end on synthetic files).
- `optimization.maximum_sharpe`: the long-only maximum Sharpe ratio (Cornuejols-Tutuncu change
  of variables).
- `data.ken_french`:
  - the 10 industry and 25 size and book-to-market portfolio files, daily and monthly;
  - sections selected by their exact title;
  - `parse_ken_french_table` for the number of firms and the average firm size.
- Study 1 report, `docs/studies/01-volatility-managed.md`, and its three configs in
  `configs/studies/` (main run, paper sample, demeaned variance), run on the Ken French data of
  2026-11-12:
  - in sample, Mkt-RF, RMW and Mom have significant positive alphas after Holm;
  - in real time and after costs, only momentum with a 2x or 5x leverage cap has a
    significantly higher net Sharpe ratio;
  - SMB and CMA become significantly worse at 25 bp.
- `qrlab.studies` (phase 5.3) with study 1, volatility-managed factors (Moreira and Muir 2017
  against Cederburg et al. 2020):
  - monthly realised variance from daily returns, the lagged inverse-variance signal (shifted
    by calendar months), full-sample and real-time scales, leverage caps and turnover costs;
  - the in-sample spanning regression with Newey-West errors and the real-time comparison of
    net Sharpe ratios (Ledoit-Wolf HAC test, stationary-bootstrap interval);
  - Holm and Benjamini-Hochberg corrections across factors, and the deflated Sharpe ratio of
    the best variant with the number of trials taken from the trial ledger;
  - an HTML report that keeps in-sample and out-of-sample results apart.
- Experiment kind `study_volatility_managed`, which runs study 1 on the six Ken French factor
  files (tested end to end on synthetic files), and `experiments.configurations_tried`.
- `qrlab.experiments` and the `qrlab` CLI (phase 5.2):
  - TOML experiment configs, with strict keys and hashed inputs;
  - a `record.json` per run (config, inputs, outputs with sample tags, code version,
    status);
  - a trial ledger that counts the distinct configurations tried;
  - the commands `qrlab run`, `validate` and `kinds`.
- Experiment kinds `portfolio_report`, `backtest` and `projection`, with example configs in
  `configs/experiments/` and synthetic inputs in `examples/data/`.
- `stats.multiple_testing` (phase 5.1): Holm, Benjamini-Hochberg and Benjamini-Yekutieli
  corrections, cross-checked against statsmodels.
- `metrics.sharpe_inference` (phase 5.1):
  - probabilistic and deflated Sharpe ratios;
  - Jobson-Korkie-Memmel and Ledoit-Wolf HAC tests of Sharpe-ratio differences;
  - a stationary-bootstrap interval for the difference.

## [0.3.0] - 2026-11-12

Milestones M3 (Risk & Planning) and M4 (Construction & Backtest): phases 3.1 to 4.4.

### Added

- `qrlab.risk` (phase 3.1):
  - covariance estimators: sample, EWMA (explicit decay and demeaning) and Ledoit-Wolf
    shrinkage, each checked to be positive semi-definite;
  - risk contributions to volatility, historical ES and normal ES, which sum to the totals;
  - Meucci's effective number of bets;
  - a factor risk model with factor and specific contributions;
  - Cornish-Fisher VaR and ES (refused when the expansion is not a quantile);
  - filtered historical simulation with an EWMA filter;
  - VaR forecasts that use only earlier data, with Kupiec and Christoffersen backtests.
- Check `diversification.effective_bets` (37 checks in total).
- `qrlab.scenarios` (phase 3.2):
  - historical replays: direct from a position's own history, by factor proxy compounded
    period by period, or reported as not covered;
  - an explicit currency effect;
  - hypothetical shocks to factors, positions and currencies;
  - scenario files in TOML (`configs/scenarios/example.toml`, example definitions).
- `qrlab.attribution` (phase 4.4):
  - Brinson-Fachler by segment (allocation, selection, interaction), linked over periods
    with Carino or reported with its residual;
  - factor attribution, with alpha and its standard error;
  - one-period currency attribution (local, currency, cross).
  - Every method adds up exactly to the active return.
- `examples/attribution_example.py`.
- `qrlab.backtest` (phase 4.3):
  - strategies see only the history up to their decision date, and an execution lag of
    at least 1 is required;
  - precomputed targets use the same lag;
  - weights drift between trades, and the 4.2 policies (or `TradeOnSignal`) decide the
    trades;
  - costs and capital-gains tax hit the net ledger, with the gross ledger alongside;
  - `summarize_backtest` reports gross and net statistics side by side.
- `examples/backtest_strategies.py`: trend and momentum strategies on synthetic data, gross
  against net.
- `qrlab.optimization` (phase 4.2):
  - explicit constraints (long-only, bounds, groups, turnover), with a feasibility check
    and a post-solve check of every constraint;
  - methods: 1/N, minimum variance, mean-variance and the efficient frontier, risk
    budgeting and ERC, maximum diversification, hierarchical risk parity, and
    Black-Litterman;
  - calendar and threshold rebalancing policies, and trade costs.
- `examples/portfolio_construction.py`: methods compared out of sample on walk-forward
  splits.
- `qrlab.validation` (phase 4.1): walk-forward splits, expanding and rolling, with
  purging of overlapping labels and an embargo. Every split checks that each training label
  ends before the first test time. A property test covers 500 random configurations.
- `qrlab.simulation` (phase 3.3):
  - Monte Carlo engines: normal and Student-t on log returns, and a block bootstrap of
    history; an explicit Generator and cell limit are required;
  - plans with contributions and net withdrawals (fixed or indexed), explicit timing,
    costs, inflation, capital-gains and wealth taxes on an average cost basis, rebalancing
    and depletion;
  - outcomes: fan charts, terminal percentiles (real, nominal, after tax), goal and
    depletion probabilities with Monte Carlo errors, sequence-of-returns risk, and a
    sensitivity table on common random numbers.
- Report section "Projection" with a fan chart, and `examples/projection_plan.py`.
- Report section "Risk and stress tests": volatility contributions, VaR and ES by method,
  and scenario results with coverage and the dates used (`RiskSummary`).
- `examples/risk_models.py`, with an integration test.
- Dev dependency `scikit-learn`, used only in tests to cross-check Ledoit-Wolf.

### Changed

- Layering: `risk` may import `core`, `stats` and `metrics`; `checks` and `reporting` may
  import `risk`. `scenarios` may import `core`, `data`, `instruments`, `metrics`, `risk`
  and `portfolio`; `reporting` may import `scenarios`.
- `build_portfolio_report` requires a `risk` argument (a `RiskSummary` or `None`) and a
  `projection` argument (a `ProjectionResult` or `None`).
- Layering: `simulation` may import `core`, `stats` and `metrics`; `reporting` may import
  `simulation`. `optimization` may import `core`, `stats`, `metrics` and `risk`.
  `backtest` may also import `optimization` and `simulation`. `attribution` may import
  `core`, `stats` and `metrics`.

## [0.2.0] - 2026-11-11

Milestones M1 (Analytics core) and M2 (Portfolio X-ray): phases 1.1 to 2.5.

### Added

- `qrlab.core` (phase 1.1):
  - `errors`: exception hierarchy (`QrlabError`, `ValidationError`, `AlignmentError`,
    `CurrencyError`, `CurrencyMismatchError`).
  - `series`: validation of time-indexed series and frames with an explicit `NanPolicy`;
    unsorted or duplicated indexes raise; `require_same_index` refuses silent alignment.
  - `calendar`: `Frequency`, a reference table of conventional periods per year (never a
    default), diagnostic `infer_frequency`, Gregorian Easter and the TARGET2 calendar.
  - `returns`: `ReturnKind`, prices to returns, simple/log conversion, excess returns,
    compounding, wealth index and aggregation with required `min_periods` and per-bucket counts.
  - `money`: `Currency`, exact `Decimal`-based `Money`, dated `FxRate` and explicit `convert`.
- `qrlab.data` (phase 1.2):
  - `store`, `provenance`, `fetch`: append-only raw store with SHA-256-verified vintages and
    JSON provenance; HTTPS-only fetcher; `Dataset` with unit, frequency, currency and
    point-in-time availability.
  - `ken_french`: FF3, FF5 and momentum factors (monthly, annual, daily), strict parser.
  - `ecb`: euro reference FX rates (with a no-forward-fill bridge to `FxRate`), €STR and
    euro-area HICP from the ECB Data Portal.
  - `user_csv`: user price files read through explicit TOML mappings
    (`configs/csv_mappings/example_prices.toml`).
- `qrlab.instruments` (phase 1.3):
  - `identifiers`: `Isin` with ISO 6166 check digits; ISO 3166-1 alpha-2 country codes.
  - `master`: `Instrument` master data (TER as a bounded fraction, fund-only fields) and
    `master_data_issues` for missing, stale, future and duplicated records.
  - `holdings`: `HoldingsSnapshot`, `holdings_issues` (weight gaps, duplicates, unknown shares,
    staleness) and the explicit `normalised_weights`.
  - `io`: TOML master data and issuer holdings CSVs through a declared mapping
    (`configs/instruments/example.toml`, `configs/csv_mappings/example_holdings.toml`).
- `qrlab.metrics` (phase 1.4):
  - `performance`: arithmetic and geometric annualised return, volatility, Sharpe ratio with
    Lo (2002) or Mertens (2002) standard errors, Sortino, downside deviation, hit rate,
    gain/loss ratio.
  - `drawdown`: drawdown series and episodes from initial wealth, maximum drawdown, Ulcer
    index, Calmar ratio.
  - `moments`: bias-corrected skewness and excess kurtosis.
  - `risk`: historical (Acerbi-Tasche ES) and normal VaR and ES, as positive one-period losses.
  - `relative`: tracking error, information ratio, CAPM regression with OLS standard errors,
    up/down capture, active share.
  - `UndefinedMetricError` instead of silent NaN or infinity.
- `qrlab.portfolio` (phase 2.1):
  - `transactions` and `ledger`: validated transactions per kind; replay into positions and
    cash per account and currency with average cost including charges (Italian "costo medio
    ponderato"); realised gains, income, costs (including FX conversion spreads), external
    flows; impossible states raise.
  - `valuation`: valuation in the base currency with explicit staleness limits for prices
    and ECB FX rates (`EcbConverter`); total-return prices refused.
  - `performance`: TWR with explicit flow timing, MWR (XIRR) with every root reported, exact
    P&L decomposition with the cash FX effect, money contribution by position, currency
    effect.
  - `broker_import`: broker exports through explicit TOML mappings
    (`configs/csv_mappings/example_broker.toml`).
- `qrlab.reporting` v1 (phase 2.3): Italian/English formatting and labels, tables,
  deterministic PNG figures, self-contained HTML rendering, and `build_portfolio_report`
  (summary with TWR and MWR kept apart, positions, cash, P&L breakdown, income and costs,
  charts, data sources and assumptions, visible warnings, "not investment advice").
- `examples/portfolio_report.py` (writes to the git-ignored `results/`), with health checks.
- `qrlab.checks` (phase 2.4): a health-check engine and 27 checks:
  - checks by category: concentration, diversification, risk, costs, ETF quality,
    currency, drift and data quality;
  - each check has a fixed direction, configurable warning and critical thresholds with
    strict comparisons, and findings that carry the numbers;
  - a missing input makes a check not applicable, with the reason; it never passes;
  - the config must list every check (`configs/checks/example.toml`, example values,
    not recommendations).
- `instruments.Instrument.fund_size` (TOML key required, `"unknown"` allowed) and
  `portfolio.TradeCharge` / `LedgerHistory.trade_charges` for the cost checks.
- `qrlab.lookthrough` (phase 2.5):
  - exposures through fund holdings by country, sector, currency (after hedging and
    underlying), security and issuer;
  - explicit buckets for unknown values, weight the holdings do not explain, funds without
    holdings, and cash;
  - pairwise fund overlap and duplicated exposure;
  - tracking difference (annualised only over a year or more, complete calendar years),
    tracking error, and TD + TER;
  - `LookThroughInputs` for checks and reports.
- Nine checks through holdings and tracking series (36 in total): country, sector and
  issuer concentration, fund overlap, duplicated exposure, tracking difference, tracking
  error, costs beyond the TER, stale holdings.
- Report section "Look-through" with holdings dates, exposures, overlap and tracking.
- Report section "Health checks" / "Controlli di salute", with names and explanations of
  every check in Italian and English (`reporting.check_labels`).
- `qrlab.stats` (phase 2.2): `ols` with classical, White and Newey-West standard errors
  (statsmodels, cross-checked with an independent implementation), `rolling_ols` without
  look-ahead, `factor_exposures` (CAPM, FF3, FF5, momentum), `stationary_bootstrap`.
- `core.returns.convert_return_currency` and the Developed/Europe Ken French factor files.
- `examples/factor_exposures.py`, with an integration test.
- `examples/portfolio_toy.py`: the hand-reconciled toy portfolio end to end, with an
  integration test.
- `data.user_csv.parse_decimal` for exact money and quantities.
- `examples/m1_analytics_core.py`: end-to-end M1 example on synthetic data, with an
  integration test.
- Dev dependency `scipy-stubs`.
- `data.user_csv.parse_number`, shared by the CSV readers.
- Design notes `docs/design/1.1-core.md`, `1.2-data.md` and `1.3-instruments.md`;
  `docs/IDEAS.md` for out-of-scope ideas.
- Dev dependency `pandas-stubs`, so mypy strict type-checks pandas code.

### Changed

- Roadmap: FRED dropped (its terms prohibit storing or caching data); ECB Data Portal used for
  rates and inflation. Broker transaction import moved from 1.2 to 2.1.
- Layering: `instruments` may import `data` (documented exception); `portfolio` may import
  `core`, `data`, `instruments` and `metrics`.
- Test helpers live in `tests/support` (pytest `pythonpath` and mypy path include `tests/`).
- CSV mappings accept a thousands separator equal to the delimiter (quoted numbers).
- pytest uses `--import-mode=importlib`, so test files in different folders may share names.
- `build_portfolio_report` requires `checks` (a `CheckResult` or `None`) and `lookthrough`
  (a `LookThroughInputs` or `None`).
- `CheckContext` requires a `lookthrough` input (`None` makes those checks not applicable).
- Layering: `lookthrough` may import `core`, `data`, `instruments`, `metrics` and
  `portfolio`; `checks` may also import `lookthrough`; `reporting` may import `checks` and
  `lookthrough`.

## [0.1.0] - 2026-11-10

### Added

- Project skeleton with `src/` layout and the `qrlab` package: documented stubs for `core`,
  `data`, `stats`, `metrics`, `validation`, `backtest` and `reporting`.
- Layering test (`tests/unit/test_architecture.py`) enforcing downward-only dependencies.
- Package and installation smoke tests; seeded `rng` fixture for deterministic tests.
- Tooling: uv with `uv.lock`, Ruff (lint and format), mypy (strict), pytest with warnings as
  errors and coverage; LF line endings enforced by `.gitattributes`.
- `.gitignore` that excludes everything under `data/` except its README.
- GitHub Actions CI on Linux and Windows for Python 3.11 and 3.13.
- Project documentation: `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`.

[Unreleased]: https://github.com/alessandroszn/quant-research-lab/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/alessandroszn/quant-research-lab/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alessandroszn/quant-research-lab/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alessandroszn/quant-research-lab/releases/tag/v0.1.0
