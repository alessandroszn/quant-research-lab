# Quant Research Lab

`qrlab` is a Python framework for quantitative financial research, empirical asset pricing,
portfolio analytics and backtesting. Correctness, reproducibility and methodological rigour come
before speed or feature count.

> **Status:** Level 0 (setup). The subpackages are documented stubs; see
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

## Data and privacy

Real portfolio data lives only in the git-ignored `data/` folder and never appears in tests,
fixtures, examples or published reports. No credentials or machine-specific paths are committed.

## Disclaimer

This is analytics and research tooling. Nothing produced by it is investment advice.
