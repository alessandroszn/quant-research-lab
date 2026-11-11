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
- Design note `docs/design/1.1-core.md`; `docs/IDEAS.md` for out-of-scope ideas.
- Dev dependency `pandas-stubs`, so mypy strict type-checks pandas code.

### Changed

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
