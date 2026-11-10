# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/alessandroszn/quant-research-lab/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/alessandroszn/quant-research-lab/releases/tag/v0.1.0
