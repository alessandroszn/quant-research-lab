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
   `src/qrlab_app` is a thin GUI with no financial logic.
7. **Minimal dependencies.** Runtime: NumPy, pandas, SciPy, statsmodels, Matplotlib. The app
   adds PySide6 as an optional extra. Each further dependency needs a documented reason.

## Target module map

Status: milestones **M1 — Analytics core**, **M2 — Portfolio X-ray** and **M3 — Risk &
Planning** are implemented:

- Level 1: `core`, `data`, `instruments` and `metrics`;
- Level 2: `portfolio`, `stats`, `reporting`, `checks` and `lookthrough`;
- Level 3: `risk`, `scenarios` and `simulation`.

Phase 4.1 `validation` (walk-forward splits with purging and embargo) is implemented too.
`backtest` exists as a documented stub. The other modules are planned (see `ROADMAP.md`), and
each one is added together with its layering rule.

| Layer | Module | Responsibility |
|---|---|---|
| 0 | `core` | Validated time series, frequencies and calendars, return conventions, currency-aware amounts, errors |
| 1 | `data` | Raw store with provenance and vintages, strict parsers; Ken French, ECB (FX, €STR, HICP), user price CSV |
| 1 | `instruments` | ETF/asset master data (ISIN, TER, domicile, replication, distribution), holdings snapshots with as-of dates |
| 2 | `stats` | HAC regressions, factor exposures, bootstrap, multiple-testing corrections, Sharpe inference |
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
| 7 | `experiments` | Config-driven runner; the single entry point |
| 7 | `cli` | `qrlab run <config>` and utilities |
| app | `qrlab_app` | PySide6 GUI; imports only `qrlab.experiments` and `qrlab.reporting` |

Rule: a module may import from modules in **lower** layers only (plus itself). Modules in the
same layer do not import each other, unless a specific exception is documented in the layering
test. Current exception: `instruments` imports `data` (raw store and provenance for loading
files); `data` never imports `instruments`.

## Quantitative risk register

| Risk | How the architecture prevents it |
|---|---|
| Look-ahead bias | Mandatory execution lag ≥ 1 in the backtest; availability dates in data; leak tests |
| Data leakage in validation | Only time-ordered splits; purging/embargo; estimation inside training folds only |
| Survivorship bias | Point-in-time universes; closed/delisted instruments retained |
| Return misalignment | Single return-convention module; validated indices; explicit alignment |
| Wrong annualisation | Periods per year always explicit; geometric vs. arithmetic distinguished |
| Currency errors | Currency-aware amounts; dated FX conversions; currency contribution reported separately |
| Wrong performance measure | TWR and MWR both computed and labelled; never mixed |
| Dividends / distributions | Total- vs. price-return flag required; accumulating vs. distributing tracked |
| Stale look-through data | Holdings carry as-of dates; checks flag staleness |
| Overfitting / multiple testing | Records log configurations tried; Holm/BH, deflated Sharpe; out-of-sample separate |
| Unrealistic costs and taxes | Cost and tax models are required inputs; gross vs. net side by side |
| Benchmark mismatch | Matching frequency, currency and return type enforced |
| Projection overconfidence | Distributions only; assumptions and parameter sensitivity shown; disclaimer |
| Numerical / silent pandas errors | Warnings are errors in tests; explicit NaN policy; independent cross-checks |
| Personal-data exposure | Real portfolios only in git-ignored `data/`; synthetic data everywhere else |

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
