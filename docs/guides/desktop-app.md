# The desktop app

The desktop app runs every analysis of the library without the command line. It is a thin layer
over the experiment runner, with no financial logic of its own. An app run and a command-line
run of the same config write identical outputs and the same `record.json`.

Start it with `qrlab-app`, which needs the `app` extra, or install the Windows program (see
{doc}`../getting-started/installation`).

## Workspaces

A workspace is a folder with three sub-folders:

| Folder | Content |
|---|---|
| `configs/` | the experiment configs (TOML) |
| `data/` | your files and the raw store; keep real data here |
| `results/` | the outputs of every run, with their records |

On the **Home** screen, open a workspace or create a new one; recent workspaces are listed
there too. The app never copies your files elsewhere, never connects to the internet and writes
no logs outside `results/`.

## Screens

| Screen | Experiment kinds |
|---|---|
| Portfolio | `portfolio_report` |
| Risk | `risk_report` |
| Scenarios | `scenario_analysis` |
| Projections | `projection` |
| Optimiser | `optimisation` |
| Backtests & studies | `backtest` and the four studies |
| Data | the raw store: source, dataset, download date, age, size, hash and terms of each file |
| History | every run, newest first, with status, configurations tried and errors |
| Settings | language, recent workspaces, version information and the settings file |

Each analysis screen has three columns:

- **Left:** the configs of its kinds, with *New from template* and *Duplicate*.
- **Centre:** a TOML editor with *Save*, *Validate* and *Run*. Validation shows the runner's
  messages unchanged.
- **Right:** the results.
  - Each table carries its sample tag (in-sample, out-of-sample or descriptive).
  - The scalars and figures are shown below the tables.
  - *Open report* and *Open folder* open them in the system's browser and file manager.

## Things to know

- **One run at a time, and runs cannot be cancelled.** The window stays responsive and shows
  the elapsed time. Closing the app during a run is refused.
- **Unsaved edits are never lost silently.** Changing config, opening another workspace,
  changing language or closing the window first asks *Save / Discard / Cancel*.
- **Re-running a config** replaces its outputs after asking. The trial ledger keeps every run.
- **Language:** English or Italian. Numbers and dates on screen follow it; files on disk never
  change. The runner's own messages and identifiers (kinds, files, tables, columns) stay as
  recorded.
- **Settings** are stored in an INI file, never in the Windows registry:
  `%APPDATA%\qrlab\qrlab-app.ini` on Windows. It holds only the language, the recent workspaces
  and the window size.
- **Shortcuts:** `Ctrl+S` saves the config and `F5` refreshes the screen.

## Self-test

`QuantResearchLab.exe --self-test WORKSPACE` (or `qrlab-app --self-test WORKSPACE`) runs every
config of a workspace through the real window, without showing it. It exits with code 0 only if
every run succeeds; a workspace without configs fails. The Windows build uses it in CI, also on
an installed copy.
