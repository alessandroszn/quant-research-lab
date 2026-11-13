# Architecture

## Design principles

1. **Pure functions over stateful objects.** Analytics take explicit inputs (validated pandas
   objects, typed records) and return new objects. Inputs are never mutated.
2. **Conventions are parameters.** Periods per year, simple vs. log returns, base currency,
   execution lag, cost and tax models are explicit arguments, never hidden defaults.
3. **Money has a currency.** Amounts in different currencies are never combined without an
   explicit, dated FX conversion.
4. **Downward-only dependencies**, enforced by `tests/unit/test_architecture.py`.
5. **One entry point.** Every analysis (portfolio X-ray, stress test, projection, backtest,
   study) is a config run by `qrlab.experiments`. Scripts, the CLI and the desktop app all go
   through it, so every result is reproducible headless.
6. **Library vs. research vs. app.** `src/qrlab` is tested and typed; `research/` is exploratory;
   `src/qrlab_app` is a thin GUI with no financial logic. The public API of `qrlab` is listed in
   `docs/api/public-api.txt` and covered by `docs/compatibility.md`.
7. **Minimal dependencies.** Runtime: NumPy, pandas, SciPy, statsmodels, Matplotlib. The app
   adds PySide6 as an optional extra. Each further dependency needs a documented reason.

## Target module map

Status: milestones **M1 — Analytics core**, **M2 — Portfolio X-ray**, **M3 — Risk &
Planning**, **M4 — Construction & Backtest** and **M5 — Research** are implemented:

- Level 1: `core`, `data`, `instruments` and `metrics`;
- Level 2: `portfolio`, `stats`, `reporting`, `checks` and `lookthrough`;
- Level 3: `risk`, `scenarios` and `simulation`;
- Level 4: `validation` (walk-forward splits with purging and embargo), `optimization`
  (constrained portfolio construction and rebalancing policies), `backtest` (lagged execution
  with gross and net ledgers) and `attribution` (Brinson-Fachler, factor and currency).

- Level 5: `stats.multiple_testing` and `metrics.sharpe_inference` (phase 5.1), `experiments`
  with the `qrlab` CLI (phase 5.2), and `studies` with four reproducible studies and written
  reports in `docs/studies/` (phase 5.3):
  - volatility-managed factors;
  - 1/N against optimised portfolios;
  - the factor zoo;
  - rebalancing for a EUR ETF investor.

Level 6 has started: the desktop app `qrlab_app` (phase 6.1: workspace, Portfolio, Risk, Scenarios,
Projections, Optimiser, Backtests & studies, Data, History and Settings screens, in English and
Italian) over `experiments.workspace` and the experiment kinds, and the Windows build
(phase 6.2: `packaging/`, a PyInstaller one-folder program with an Inno Setup installer, checked
in CI against the source). v1.0 is planned (see `ROADMAP.md`); each new module is added
together with its layering rule.

| Layer | Module | Responsibility |
|---|---|---|
| 0 | `core` | Validated time series, frequencies and calendars, return conventions, currency-aware amounts, errors |
| 1 | `data` | Raw store with provenance and vintages, strict parsers; Ken French, ECB (FX, €STR, HICP), user price CSV |
| 1 | `instruments` | ETF/asset master data (ISIN, TER, domicile, replication, distribution), holdings snapshots with as-of dates |
| 2 | `stats` | HAC regressions, fixed-effects panel regressions with clustered errors, factor exposures, bootstrap, multiple-testing corrections |
| 2 | `metrics` | Performance, risk and benchmark-relative metrics with standard errors |
| 3 | `risk` | Covariance estimators, risk decomposition, factor risk model, VaR/ES and VaR backtests |
| 3 | `validation` | Walk-forward, purged and embargoed time-series splits |
| 4 | `portfolio` | Transactions → positions and cash; multi-currency valuation; TWR, MWR (XIRR), contribution |
| 4 | `optimization` | 1/N, min-variance, mean-variance, risk parity, max diversification, Black–Litterman, HRP; rebalancing policies |
| 5 | `checks` | Health-check rule engine and rule library (explanations live in `reporting.check_labels`) |
| 5 | `lookthrough` | Exposures through ETF holdings, overlap, tracking difference, cost analysis |
| 5 | `scenarios` | Historical replays and hypothetical shocks |
| 5 | `simulation` | Monte Carlo projections, goal and savings-plan planning |
| 5 | `attribution` | Brinson–Fachler, factor and currency attribution |
| 5 | `backtest` | Signal → weights → P&L with mandatory execution lag and costs |
| 6 | `reporting` | Tables, figures, HTML/PDF reports, experiment records |
| 6.5 | `studies` | Empirical studies (pure functions + report), each run by an experiment kind |
| 7 | `experiments` | Config-driven runner; the single entry point |
| 7 | `cli` | `qrlab run <config>` and utilities |
| app | `qrlab_app` | PySide6 GUI; imports only `qrlab.experiments` and `qrlab.reporting` |

Rule: a module may import from modules in **lower** layers only (plus itself). Modules in the
same layer do not import each other, unless a specific exception is documented in the layering
test. Current exception: `instruments` imports `data` (raw store and provenance for loading
files); `data` never imports `instruments`.

## Quantitative risk register

What qrlab actually does about each risk, and the main gap that remains. Each methodology page
in the documentation (`docs/methodology/`) gives the example, the mechanisms, the tests that
guard them and every known limit. This table was corrected for 1.0 (design note 6.3b), where
earlier versions promised more than the code does.

| Risk | What qrlab does | Main gap |
|---|---|---|
| Look-ahead bias | Execution lag required (≥ 1, no default) in the backtest; walk-forward decisions use only past returns | Availability dates exist only for some ECB series and are not used downstream; a strategy can still leak data it captures itself |
| Data leakage in validation | Time-ordered splits only, with purging and embargo, checked on every split (`qrlab.validation`) | The backtest and studies use their own trailing windows, not `qrlab.validation`; estimation inside folds is left to the caller |
| Survivorship bias | Missing returns are never filled; uncovered stress-test positions are excluded, not zeroed; fund age and size checks | No point-in-time universes and no delisting handling; the backtest needs a fixed, complete panel |
| Return misalignment | Validated, sorted, unique indices; explicit alignment (`require_same_index`) | The return kind is not carried by a series; metrics assume simple returns by contract |
| Wrong annualisation | `periods_per_year` always explicit; geometric and arithmetic returns are separate functions | `periods_per_year` is not checked against the data's frequency; √P scaling assumes no autocorrelation |
| Currency errors | Currency-aware amounts; dated ECB FX conversions; cash FX shown separately in the P&L breakdown | The `portfolio_report` kind is single-currency; FX effects of positions stay inside their P&L |
| Wrong performance measure | TWR and MWR computed separately, labelled, never mixed in one number | The MWR is always annual while a short-period TWR is not; the record stores only the TWR |
| Dividends / distributions | Price type required for user price files and tracking series; valuation refuses total-return prices | Returns CSVs of the backtest, risk, optimisation and scenario kinds carry no price-type flag; no ex-dates |
| Stale look-through data | Holdings carry as-of dates; future-dated holdings are refused; stale ones are flagged by checks | Stale holdings are flagged, not refused; the `portfolio_report` kind does not run look-through |
| Overfitting / multiple testing | Trial ledger and `configurations_tried` in every record; Holm/BH/BY; deflated Sharpe in studies 1 and 2; sample tags | The count covers only runs through the runner; tags are checked for validity, not truth |
| Unrealistic costs and taxes | Cost and tax models have no defaults; gross and net side by side in backtests | Linear costs only; one flat capital-gains rate without loss offsets; zero costs are accepted |
| Benchmark mismatch | Tracking difference and error check currency, hedging and price type | Relative metrics and attribution check dates only; currency and return type are left to the caller |
| Projection overconfidence | Distributions only, with Monte Carlo standard errors; optional parameter sensitivity | Sensitivity can be switched off; the `projection` kind's files carry no disclaimer |
| Numerical / silent pandas errors | Warnings are errors in tests; explicit NaN policy; cross-checks against statsmodels, SciPy and scikit-learn | Warnings are errors only under pytest; cross-checks cover selected functions |
| Personal-data exposure | Real portfolios only in git-ignored `data/`; synthetic data in examples and tests | Protected by `.gitignore` and convention; no automated check yet (the 6.3c audit adds one before publication) |

## Testing strategy

- **Unit tests** with hand-calculated examples and analytical benchmarks.
- **Property tests** on seeded synthetic data. Examples: no-overlap of train and test windows;
  risk contributions sum to the total; Monte Carlo convergence.
- **Cross-checks** against statsmodels and SciPy.
- **Reconciliation tests:** a hand-built toy portfolio whose every number is checked by hand.
- **Edge cases:**
  - empty, all-NaN or single-observation series;
  - zero variance;
  - unsorted or duplicated index;
  - mixed currencies.
- **Integration tests** for end-to-end configs; an off-screen smoke test for the app; the built
  `.exe` runs a sample analysis in CI.
- **Quality gate:** the architecture (layering) test; pytest with `filterwarnings = error`;
  mypy strict; Ruff lint and format; CI on Linux and Windows.
