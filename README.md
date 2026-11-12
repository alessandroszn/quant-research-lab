# Quant Research Lab

`qrlab` is a Python framework for quantitative financial research, empirical asset pricing,
portfolio analytics and backtesting. Correctness, reproducibility and methodological rigour come
before speed or feature count.

> **Status:** milestone M1 (Analytics core) reached: `core`, `data`, `instruments` and
> `metrics` are implemented and tested; the other subpackages are documented stubs. See
> [`docs/ROADMAP.md`](docs/ROADMAP.md) for the plan and [`CHANGELOG.md`](CHANGELOG.md) for
> releases.

## Pillars

1. **Portfolio & ETF analytics** — time- and money-weighted performance, risk, factor and
   look-through exposures, ETF overlap and costs, health checks, stress tests and Monte Carlo
   projections.
2. **Research lab** — portfolio optimisation, look-ahead-free backtests, attribution and
   reproducible studies on public data.
3. **Desktop app** — a Windows application on top of the same library, with no financial logic
   of its own.

## Requirements

- Python ≥ 3.11 (development uses the version in `.python-version`)
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

Reading Parquet files (study 3, Open Source Asset Pricing data) needs the optional extra:
`uv sync --extra parquet` (`pyarrow`; also part of the dev environment).

## Quality gate

Every change must pass:

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
```

CI runs the same checks on Linux and Windows for Python 3.11 and 3.13.

## Layout

| Path | Contents |
|---|---|
| `src/qrlab/` | The library: tested, typed, layered (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)) |
| `tests/` | Unit, property and integration tests (deterministic, no network) |
| `configs/` | Experiment configurations |
| `examples/` | Small runnable examples on synthetic data |
| `research/` | Exploratory work, not part of the library |
| `data/` | Local data store, git-ignored except its README |

## Example

```bash
uv run python examples/m1_analytics_core.py
```

Synthetic prices in an Italian broker CSV format are imported with provenance, converted to
returns and analysed (CAGR, volatility, Sharpe with standard error, drawdown, VaR/ES, tracking
error, CAPM, capture ratios). Offline and deterministic.

```bash
uv run python examples/portfolio_toy.py
```

A synthetic broker export is imported, replayed into positions and cash, valued, and measured
with a time-weighted return, a money-weighted return (XIRR) and an exact P&L decomposition.

```bash
uv run python examples/portfolio_report.py
```

Writes a self-contained HTML report of the same synthetic portfolio (Italian by default, `en`
as second argument for English) to `results/`, which is git-ignored.

## Data and privacy

Real portfolio data lives only in the git-ignored `data/` folder and never appears in tests,
fixtures, examples or published reports. No credentials or machine-specific paths are committed.

## Disclaimer

This is analytics and research tooling. Nothing produced by it is investment advice.
