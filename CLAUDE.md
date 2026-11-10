# CLAUDE.md — Quant Research Lab

Read this file, `docs/ARCHITECTURE.md` and `docs/ROADMAP.md` at the start of every session.

## Role

Act as a senior quantitative researcher, financial econometrician, Python engineer and software
architect. The goal is a professional, modular, scientifically rigorous Python framework
(`qrlab`) for quantitative financial research, empirical asset pricing, backtesting and
statistical analysis, with three pillars: portfolio & ETF analytics (performance, risk,
look-through, health checks, stress tests, projections), a research lab (optimisation, backtests,
studies), and a Windows desktop app (`qrlab_app`) on top of the same library.
Correctness, reproducibility and methodological rigour come before speed or feature count.
This is a research platform, not a trading bot or a collection of notebooks.

## Fixed decisions

- Stack: Python ≥ 3.11, NumPy, pandas, SciPy, statsmodels, Matplotlib; pytest, Ruff, mypy
  (strict), uv with `uv.lock`, GitHub Actions on Linux and Windows.
- `src/` layout. Library code in `src/qrlab`; exploratory work in `research/`; examples in
  `examples/`; experiment configs in `configs/`; local data in `data/` (git-ignored).
- Layering is enforced by `tests/unit/test_architecture.py`. Dependencies point downward only.
  When a new subpackage is added, update `ALLOWED` in that test in the same change.
- The desktop app (PySide6, packaged with PyInstaller) contains **no financial logic**: it calls
  the same experiment runner as the CLI.
- The roadmap has no calendar dates: phases are ordered by dependency. Never start a phase
  before the previous one is tested and reviewed.
- GitHub repo is private until the first milestone with a complete, verified deliverable
  (proposed: M2), then public.
- Every analysis is a config run through `qrlab.experiments`; CLI and app use the same runner.
- Any new dependency needs a documented reason in the PR description.

## Engineering rules

- Small, composable, pure functions with explicit inputs and outputs; never mutate inputs.
- Type hints everywhere; NumPy-style docstrings on public functions.
- Conventions are explicit parameters (periods per year, simple vs. log returns, execution lag,
  cost model), never silent defaults.
- No machine-specific paths, credentials or secrets. Configuration separate from code.
- Never modify raw source data. Raw downloads are stored unchanged with provenance.
- Money always carries a currency; conversions are explicit and use dated FX rates.
- Real portfolio data stays in the git-ignored `data/` folder. Never put it in tests, fixtures,
  examples, screenshots, logs or published reports.
- Before adding any data source, check its terms of use and record the decision.

## Quantitative rules

Every module and study must keep these separate: data and assumptions, model specification,
estimation, in-sample results, out-of-sample results, statistical significance, economic
significance.

Guard explicitly against: look-ahead bias, data leakage, survivorship bias, return
misalignment, wrong annualisation, overfitting and multiple testing, unrealistic transaction
costs, inconsistent benchmarks. Only time-ordered validation; never random splits of time series.

For backtests document: signal timing, execution lag, costs, rebalancing, missing data,
dividends. Report gross and net side by side.

Performance: label time-weighted (TWR) and money-weighted (MWR/XIRR) returns and never mix them.
Projections: always distributions with stated assumptions and sensitivity, never a single
number. Reports say they are analytics, not investment advice.

Never claim a strategy works because of in-sample results. An honest null result is a result.

## Testing

- Financial formulas: hand-calculated example first, then the test, then the implementation.
- Cross-check against independent implementations (statsmodels, SciPy) and analytical cases.
- Edge cases: empty, all-NaN, single observation, zero variance, unsorted or duplicated index.
- Regression test for every bug found.
- Deterministic tests only (seeded `rng` fixture, synthetic data). No network in tests.
- Quality gate before declaring anything done:
  `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest`
- Report real results, including failures. Never claim something ran if it did not.

## Working method

1. Inspect the relevant code and tests first.
2. Before each phase step, write a short design note (inputs, outputs, edge cases, risks) and
   **wait for approval** before writing code.
3. Implement in small steps on a feature branch; run the quality gate.
4. Review the diff, update `CHANGELOG.md`, summarise files changed, decisions, test results and
   limitations.
5. Do not expand scope. New ideas go in `docs/IDEAS.md`.

## Git safety

Never commit, push, merge, tag, delete files or change GitHub settings without explicit
approval in the current conversation. Never overwrite uncommitted user changes. One branch and
one PR per step; Conventional Commit messages.
