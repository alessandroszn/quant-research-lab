# Personal-data exposure

A real portfolio is personal financial data: holdings, amounts, dates, broker and account
details. Once such a file is committed, it stays in the git history even after it is deleted,
and anyone who can read the repository can read it. Run outputs are as sensitive as the inputs,
because they contain values computed from them.

## How it goes wrong

A user runs the portfolio report on their own broker export and saves the run folder next to the
code. Besides `report.html`, the folder holds `record.json`, which by design records everything
needed to reproduce the run. For a real portfolio it would contain, for example (values
invented):

```json
{
  "config": {"path": "C:\\Users\\<name>\\...\\my_report.toml", "content": {"...": "..."}},
  "inputs": {"transactions": {"resolved": "C:\\Users\\<name>\\...\\broker_2026.csv",
                              "sha256": "...", "bytes": 48213}},
  "scalars": {"end_value": {"value": 152340.0, "tag": "descriptive"}}
}
```

Committing that folder publishes the portfolio's value, its time-weighted return and the
Windows user name in the paths, even if the broker export itself was never committed.

## How qrlab prevents it

- `.gitignore` ignores everything under `data/` except `data/README.md`, plus `results/`,
  `reports/`, `*.xlsx`, `*.xls`, `.env` files and key files. Run outputs of the example configs
  go to `results/`.
- `data/README.md` describes the local layout: `raw/` (downloads exactly as received),
  `interim/` and `processed/`. Nothing else in `data/` is committed.
- The examples and tests use synthetic data. `examples/data/` holds a made-up broker export,
  prices and stress inputs for invented ISINs such as `IE0000000012`. The shared test fixtures in
  `tests/support/portfolio.py` are synthetic, and all random test data comes from the seeded
  `rng` fixture in `tests/conftest.py`.
- The example configs say how to use real data: copy the config, point `[inputs]` at files
  under `data/` and keep the copy there (`configs/README.md`,
  `configs/experiments/example_portfolio_report.toml`).
- The HTML portfolio report ends with "This report may contain personal financial data: keep it
  private." It is a single self-contained file with no external links, so opening it contacts
  no server.
- The desktop app works in workspaces: folders the user chooses, each with `configs/`, `data/`
  and `results/` ({py:func}`qrlab.experiments.workspace.create_workspace`). It has no financial
  logic and does not store portfolio data of its own.
- The app's settings are an INI file, `%APPDATA%\qrlab\qrlab-app.ini` on Windows, never the
  registry. It holds the interface language, up to eight recent workspace folders and the window
  geometry. The Settings screen shows where the file is and can remove or clear the recent
  folders. Uninstalling removes the program folder only; settings and workspaces are kept.
- The app's `--self-test`, used by the Windows build in CI, keeps its settings in memory and
  runs on a copy of the synthetic examples.
- The experiment runner, the CLI and the app make no network calls. Downloads exist only in
  `qrlab.data` for public datasets, called explicitly.

## What guards it

- `tests/unit/app/test_app_smoke.py`: `test_settings_file_round_trip` (the store is an INI
  file; a native-format store, which is the registry on Windows, raises),
  `test_recent_workspaces_on_home_and_settings`.
- `tests/unit/app/test_language_settings.py`: `test_recent_workspaces` (at most eight, forget,
  clear), `test_geometry_round_trip`.
- `tests/unit/app/test_selftest.py`: `test_self_test_runs_every_config`, with a fixture that
  fails the test if the self-test opens the user's settings file.
- `tests/unit/experiments/test_workspace.py`: `test_create_workspace`.
- `tests/unit/reporting/test_portfolio_report.py`: `test_report_is_self_contained`.
- `tests/integration/test_examples.py`: the examples run on synthetic data and reproduce hand
  values, for example `test_portfolio_example_reproduces_the_hand_values`.

## Limits

- The protection is `.gitignore` plus convention. No test or CI step checks that no real data
  is tracked, or that fixtures and examples are synthetic. `git add -f` overrides `.gitignore`,
  and a file saved outside the ignored folders (for example a CSV in `configs/` or `research/`)
  is not ignored. CSV files are not ignored by extension.
- Run outputs are private only if they are written to an ignored folder. The output directory
  is set in each config and can point anywhere.
- Records and reports of real portfolios contain personal data: values, returns, the full
  config and absolute input paths. Only the HTML portfolio report carries the "keep it private"
  note; the CSV tables, PNG figures and `record.json` do not. No test checks the note.
- The settings file stores absolute folder paths, which may reveal a user name or folder names.
  It survives uninstalling.
- Screenshots, logs and published reports are covered by the project rules only, not by code.
- Nothing is encrypted at rest. Access to `data/`, workspaces and `results/` is governed by the
  file system.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
