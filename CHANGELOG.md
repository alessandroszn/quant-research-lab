# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Notices that travel with the outputs (phase 7.2). The `projection`, `optimisation`,
  `scenario_analysis` and `backtest` kinds now state what their outputs are not: a forecast, a
  recommendation or a probability of loss. Each notice ends with "Research analytics, not
  investment advice."
  - **Where it appears:** `NOTICE.txt` in the output folder (tagged `descriptive`), a new
    `"notice"` field in `record.json` (`null` for the other kinds), the `qrlab run` output and
    the app's results panel. `RECORD_FORMAT` stays 1: the field is an addition.
  - **In the figure:** the projection fan chart carries a footer, "Scenarios from stated
    assumptions, not a forecast.", through the new `line_figure(note=...)` parameter. Without a
    note, figures are byte-identical to before.
  - **Sensitivity off:** a projection run with `sensitivity = false` says so in its notice.
  - `ExperimentOutput` gains `notice: str | None = None`.
- `qrlab.core.require_periods_per_year` (phase 7.1): a `periods_per_year` that contradicts the
  dates' frequency now raises, with the value to use. For example, 252 on monthly data raises
  with "use 12".
  - **Where it applies:** every annualising metric, `factor_exposures`, the tracking error,
    `summarize_backtest`, and the `risk_report` and `optimisation` kinds.
  - **When it does not:** series whose dates have no recognisable frequency are not checked.

### Changed

- **Breaking for 1.0.0rc1 configs:** the returns files of four kinds must declare whether
  they include dividends (phase 7.3).
  - **The new required key:** `returns_price_type` in `backtest`, `optimisation` and
    `risk_report`, and `position_returns_price_type` in `scenario_analysis`. A config without
    it fails validation and names the key.
  - **Values:** `"total_return"` or `"price"`. `"nav"` is refused, because a NAV return
    includes the income of an accumulating fund but not of a distributing one; the message
    says which to declare.
  - **What it does:** the declaration changes no number. With `"price"`, the run's notice says
    that return levels are understated by about the dividend yield. `risk_report` has a notice
    only in that case.
  - **Why required:** a default would be the silent assumption this removes. 1.0.0 is not
    released, so it is not a 2.0 change. The example configs declare `"total_return"`.

### Fixed

- The beta health check passed `periods_per_year=1` whatever the frequency of the returns. Its
  result was unaffected, because only the unused alpha is scaled; it now passes the value that
  matches the dates (regression test).

### Added

- The working paper (phase 6.3d), *What survives? Four reproducible studies of portfolio rules
  under real-time implementation, costs and multiple testing*, in `docs/paper/` and on the
  documentation site.
  - **Numbers come from the records.** `scripts/paper_values.py` generates every number and
    table from the study records, as declared in `docs/paper/values/*.toml`; the text uses MyST
    substitutions only.
  - **Checks.** `--check` regenerates from the records and fails on any difference, and a test
    requires every generated value to be used and every substitution to be defined.
  - **Reproducibility appendix.** Run dates, versions, commits, seeds, configurations tried and
    the exact data files with their hashes.

### Changed

- The four studies were re-run from a clean checkout of commit 63f808a, with the same data
  files and trial ledgers: all nine runs gave byte-identical outputs. The paper's reproducibility
  appendix now cites these records, and the reports note the re-run.

### Fixed

- Last-digit figures in the study reports, found while generating the paper from the records:
  - **Study 1:** RMW z 1.46, Holm 0.71, mean weight 0.77; CMA z −0.66; momentum at 2× and
    25 bp 0.78.
  - **Study 2:** the HRP CEQ gap is 0.6–0.9 % a year. Sample maximum Sharpe on D1 is below 1/N
    everywhere, but BL maximum Sharpe is as low, so it is not "the lowest".
  - **Study 3:** 87 % of clear predictors are positive after publication, not 86 %.
  - **Study 4:** five shares that end in exactly 5 are now rounded half-up, as everywhere else.

### Changed

- The Windows build no longer runs on every push to `main`, nor on PRs that change only
  `pyproject.toml`. It still runs for every release, on PRs that change the packaging, its
  workflow or `uv.lock`, and by hand. This saves Actions minutes: a run takes 6-7 minutes on
  Windows runners.

## [1.0.0rc1] - 2026-11-13

Release candidate of version 1.0 (milestone M6, phases 6.1 to 6.3c). It brings:

- the desktop app;
- the Windows program and installer;
- a frozen public API with a compatibility policy;
- the documentation site;
- the release automation.

It is published to TestPyPI to check the release process; 1.0.0 follows with the same code if
nothing is found.

### Added

- Release preparation (phase 6.3c):
  - **Licence:** the BSD-3-Clause `LICENSE`; documentation and study reports under CC BY 4.0.
  - **Citation:** `CITATION.cff` and `.zenodo.json`.
  - **Community files:** `CONTRIBUTING.md` and `SECURITY.md`.
  - **Release workflow:** on a version tag, `release.yml` checks the tag against the version,
    builds and tests the sdist, the wheel and the Windows program, drafts a GitHub Release, and
    publishes to TestPyPI (release candidates) or PyPI by trusted publishing, after the owner's
    approval.
  - **Docs deployment:** `docs-pages.yml` publishes the documentation to GitHub Pages on final
    tags.
  - **Release guide:** `docs/project/releasing.md`.
- `scripts/audit_history.py`: scans every file version in the git history for private data
  files, spreadsheets, secrets, IBANs, e-mail addresses and the ISINs of the real portfolio
  (read locally from a git-ignored folder). It reports paths and counts only.
- `scripts/readme_figures.py`: the README figures, drawn from the study records.

- Documentation site (phase 6.3b), built with Sphinx, MyST-Parser and pydata-sphinx-theme:
  - getting started, and guides to experiments, the experiment kinds, the desktop app,
    reproducing the studies and the data sources;
  - one methodology page per risk in the risk register, each with its limits; the register in
    `ARCHITECTURE.md` is corrected where it promised more than the code does;
  - the four studies;
  - the API reference generated from the docstrings;
  - the changelog, the architecture, the roadmap and the design notes.

  A new `docs` job in CI builds it with warnings as errors and runs the guides' examples as
  doctests, without network access.
- `qrlab.data` now exports the Open Source Asset Pricing functions used by study 3:
  `download_osap`, `parse_long_short_returns`, `parse_signal_doc`, `OSAP_FILES` and
  `OSAP_REVISION`.
- New dependency group `docs` (Sphinx, myst-parser, pydata-sphinx-theme). Reason: the
  documentation tool chosen in design note 6.3 (D3); not a runtime dependency.

- The public API is frozen for 1.0 (phase 6.3a):
  - `docs/api/public-api.txt` lists every public name with its signature, and
    `tests/unit/test_public_api.py` fails on any change that is not reflected there;
  - `docs/compatibility.md` states the Semantic Versioning promise, what is and is not public,
    and the deprecation rule.
- `qrlab.experiments.RECORD_FORMAT`: every `record.json` now has `"format": 1`.

- Windows build (phase 6.2), in `packaging/`, built by the new workflow
  `.github/workflows/app-build.yml`:
  - **Contents:** a PyInstaller one-folder build holding `QuantResearchLab.exe` (the app) and
    `qrlab.exe` (the command line), with `build-info.json`, `THIRD_PARTY_NOTICES.txt` and the
    LGPL/GPL texts.
  - **Deliverables:** a per-user Inno Setup installer that needs no administrator rights and
    never touches workspaces or settings, a portable zip, and `SHA256SUMS.txt`, uploaded as
    workflow artifacts.
  - **CI checks:** the six examples run from source and from the frozen `qrlab.exe` must give
    byte-identical outputs. The frozen app's self-test must pass, both from the build folder
    and after a silent install. Uninstalling must remove the program and keep the workspace.
- `QuantResearchLab.exe --self-test WORKSPACE` (`qrlab_app.selftest`): runs every config of a
  workspace through the real window, without showing it. It exits with 0 only if all runs
  succeed; an empty workspace fails.
- New dependency group `build` (`pyinstaller` 6.22). Reason: the roadmap's packaging tool. It
  is GPL-2.0 with the bootloader exception, and it is not a runtime dependency.

- The app in Italian and English (phase 6.1c):
  - every app string, error message, sample tag and run status is in both languages;
  - numbers and dates on screen follow the language (`0,0317`, `1.234.570`, `12/11/2026`);
    missing values show as `—`, and the files on disk never change;
  - the runner's messages and all identifiers (kinds, files, tables, columns, scalars) stay as
    recorded.
- The app's Settings screen: language (applied at once by rebuilding the window, never during a
  run), recent workspaces, version information and where the settings file is. Settings live in
  an INI file (`%APPDATA%/qrlab/qrlab-app.ini` on Windows), not in the registry.
- Recent workspaces on the Home screen (at most 8; missing folders are marked and cannot be
  opened). The window title shows the open workspace, and the window size is remembered.
- `reporting.formatting.format_significant`: significant figures with the language's
  separators, half-up on the decimal value, scientific notation outside `[1e-4, 1e12)`.

- Experiment kinds for the app's Risk, Scenarios and Optimiser screens (phase 6.1b), thin
  adapters over tested library functions, each with a synthetic example config:
  - `risk_report`: covariance (sample, EWMA, Ledoit-Wolf), contributions to volatility and to
    historical and normal ES, VaR/ES by four methods (Cornish-Fisher left empty with its
    reason when not a quantile), and a VaR backtest with Kupiec and Christoffersen tests;
  - `scenario_analysis`: phase 3.2 stress tests from a holdings CSV, with optional position
    returns, factors, betas and FX;
  - `optimisation`: 1/N, minimum variance, mean-variance, maximum Sharpe, risk parity,
    maximum diversification and HRP, in sample, with bounds.
- Optional inputs for experiment kinds (`ExperimentKind.optional_inputs`); the CLI and config
  templates list them.
- The app's Risk, Scenarios and Optimiser screens.
- Desktop app `qrlab_app` (phase 6.1a, PySide6), started with `qrlab-app`:
  - Home (open or create a workspace), Portfolio, Projections, Backtests & studies, Data and
    History screens;
  - a TOML editor with Validate and Run;
  - runs in a worker thread, one at a time, with confirmation before outputs are replaced;
  - results with their sample tags, scalars and figures;
  - the report and folder open in the system browser.

  There is no financial logic in the app: a test enforces that it imports only
  `qrlab.experiments` and `qrlab.reporting`. Qt-free view-models are unit-tested; an off-screen
  smoke test runs an experiment end to end.
- `experiments.workspace`: `create_workspace`, `list_configs` (with validation status),
  `list_runs`, `list_raw_files` (provenance and age) and `config_template`.
- Optional extra `app` (`PySide6-Essentials`, also in the dev group). Reason: the roadmap's GUI
  toolkit; "Essentials" avoids the large add-ons such as QtWebEngine.

### Changed

- The README is rewritten for the public release: status, features, the four studies with two
  figures, install, quality, data and privacy, citation and licence. Its links are absolute,
  so they also work on PyPI.
- `pyproject.toml` declares the licence (PEP 639), keywords, classifiers and project URLs, and
  no longer blocks uploads.
- The Windows build is reusable (`workflow_call`): release tags now build it through
  `release.yml`.
- **Breaking:** `qrlab.stats.FactorModel` is renamed to `qrlab.stats.FactorSet`, so it is no
  longer confused with the factor risk model `qrlab.risk.FactorModel`. It is the only rename
  from the review of the 341 public names before the API freeze.
- Run records gain `code.frozen`. In a frozen program the commit comes from the bundled
  `build-info.json`, with the build time in `code.built`, and `git` is never started. A missing
  or incomplete file refuses the run before anything is written.
- CI installs the Qt system libraries on Linux for the off-screen app tests.
- The app no longer loses unsaved edits: changing config, creating or duplicating one, opening
  another workspace, changing language or closing the window first asks *Save / Discard /
  Cancel*. Closing the window during a run is refused, because runs cannot be cancelled.
- App editor: monospace font without line wrapping; `Ctrl+S` saves and `F5` refreshes the
  screen.

## [0.4.0] - 2026-11-12

Milestone M5 (Research): phases 5.1 to 5.3. There are four reproducible studies with written
reports in `docs/studies/`, each run on real data through the experiment runner:

- volatility-managed factors;
- 1/N against optimised portfolios;
- the factor zoo;
- rebalancing for a EUR ETF investor.

### Added

- Study 4 report, `docs/studies/04-rebalancing.md`, and its two configs in `configs/studies/`
  (60/40 and 80/20), run on Ken French and ECB data of 2026-11-12, October 2004 to September
  2026:
  - monthly rebalancing ends with about €14k less after tax than annual over 20 years (worse in
    99.9 % of paths);
  - buy-and-hold ends richer in 84 % of paths, but drifts to about 86 % equity with more
    volatility and deeper drawdowns;
  - a 5-point band trades far less than quarterly but tracks the target like annual
    rebalancing, so H1 is not supported.
- Study 4 (phase 5.3), rebalancing rules for a EUR ETF investor after costs, Italian tax and
  currency:
  - `qrlab.studies.rebalancing`:
    - world equity converted to EUR at ECB month-end rates;
    - a rolled 7-year AAA zero-coupon bond built from continuously compounded ECB spot rates;
    - seven policies (buy-and-hold, three calendars, three bands) run through the backtest
      engine;
    - after-tax wealth with liquidation tax, and path metrics;
    - stationary-bootstrap paths shared by all policies, paired comparisons and hypothesis
      shares;
    - an HTML report;
  - experiment kind `study_rebalancing`, tested end to end on synthetic files.
- `data.ecb`: AAA euro-area spot rates at 6 and 7 years (`yc_aaa_spot_6y`, `yc_aaa_spot_7y`)
  and `parse_yield_curve`.
- `backtest.BacktestResult.final_basis`: net-ledger cost basis per asset at the end.

- Study 3 report, `docs/studies/03-factor-zoo.md`, and its two configs in `configs/studies/`
  ("clear" and "clear and likely" predictors), run on OSAP release 2026.10:
  - in their original samples, 92.5 % of "clear" predictors pass a single test, 63 % pass
    t > 3 and 52 % pass Holm;
  - returns are 35 % lower after the sample and 58 % lower after publication;
  - the post-publication composite is still positive (0.68 % per month, t = 6.0).
- `studies.factor_zoo.gap_shares`; the factor-zoo kind excludes and lists predictors with more
  than 1 % missing months (approved deviation).
- Study 3 (phase 5.3), the factor zoo (Harvey, Liu and Zhu 2016; McLean and Pontiff 2016) on
  Open Source Asset Pricing data:
  - `qrlab.studies.factor_zoo`:
    - phases of each predictor (original sample, post-sample, post-publication);
    - per-predictor Newey-West tests and counts under single-test, t > 3, Holm, BH and BY
      rules;
    - the McLean-Pontiff decay regression;
    - equal-weighted composites by phase;
    - an HTML report;
  - experiment kind `study_factor_zoo`, tested end to end on synthetic files.
- `data.open_asset_pricing`: pinned downloads into the raw store and strict parsers for the
  predictor long-short returns (Parquet) and `SignalDoc.csv`. The terms (CC BY 4.0) are
  recorded in the data-source table.
- `stats.panel`: fixed-effects OLS with cluster-robust errors and linear contrasts,
  cross-checked against statsmodels with dummies.
- Optional extra `parquet` (`pyarrow`), also in the dev group. Reason: OSAP publishes returns
  only as Parquet.

- Study 2 report, `docs/studies/02-one-over-n.md`, and its two configs in `configs/studies/`
  (main run and paper period), run on the Ken French data of 2026-11-12:
  - no optimised strategy has a significantly higher net Sharpe ratio than 1/N after Holm
    (H1 supported);
  - shrinkage and Black-Litterman do not significantly improve on sample estimates (H2 not
    supported).
- `data.ken_french.AVERAGE_MARKET_CAP`: the 25 size/BM file names its size section
  "Average Market Cap".

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

### Fixed

- `data.open_asset_pricing.parse_signal_doc` refused the real release 2026.10: it has a "Drop"
  category, "indirect" predictability and missing signs for non-predictors. Only predictors
  are strict now. Regression test added.
- `optimization.maximum_sharpe` accepted only a solver success. SLSQP can stop at the optimum
  with a line-search status: this happened in 2 of about 4,000 real Black-Litterman inputs.
  The function now also accepts a feasible point that meets the KKT conditions of the convex
  problem, which makes it the global optimum. Regression tests added.
- The 25 size/BM portfolio file was read with the wrong size-section title; the strict parser
  refused it, and no data was misread. Regression test added.

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

[Unreleased]: https://github.com/alessandroszn/quant-research-lab/compare/v1.0.0rc1...HEAD
[1.0.0rc1]: https://github.com/alessandroszn/quant-research-lab/compare/v0.4.0...v1.0.0rc1
[0.4.0]: https://github.com/alessandroszn/quant-research-lab/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/alessandroszn/quant-research-lab/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alessandroszn/quant-research-lab/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alessandroszn/quant-research-lab/releases/tag/v0.1.0
