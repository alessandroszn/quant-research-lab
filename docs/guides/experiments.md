# Experiments, configs and records

Every analysis is an **experiment**: a config file run by
{py:func}`qrlab.experiments.run_experiment`. The command line, the desktop app and scripts all
call this same runner. An analysis is therefore reproducible from its config alone, and none of
them can compute anything the others cannot.

## The config

A config is a TOML file with four tables:

```toml
[experiment]
name = "example-risk-report"   # identifies the experiment in the trial ledger
kind = "risk_report"           # one of `qrlab kinds`
hypothesis = "descriptive"     # what the run is meant to show, in words
# seed = 20261113              # required by kinds that draw random numbers, refused otherwise

[inputs]                        # local files, relative to the config file
returns = "../../examples/data/asset_returns.csv"

[parameters]                    # kind-specific; see the experiment kinds guide
confidence = 0.95
periods_per_year = 12

[output]
directory = "../../results/example-risk-report"
```

- **Unknown keys raise.** A typo is never silently ignored, and the same holds for unknown
  inputs.
- **Groups of files.** A kind may accept a table of files with free keys instead of a single
  file. For example, the `portfolio_report` kind takes one extra price file per currency:
  ```toml
  [inputs.extra_prices]
  usd = "../../examples/data/prices_usd.csv"

  [inputs.extra_prices_mapping]
  usd = "../../examples/data/prices_usd_mapping.toml"
  ```
  Each file is recorded as `<group>.<key>` (here `extra_prices.usd`), with its SHA-256, like
  any other input. Keys must be non-empty and contain no dot; `qrlab kinds` lists the groups
  each kind accepts.
- **Conventions are explicit.** Periods per year, the date format and decimal separator of
  input files, execution lags and cost models are parameters. Nothing is guessed.
- **Templates.** `qrlab.experiments.workspace.config_template` writes a commented template for
  any kind; the desktop app's *New from template* uses it.

## Running

| Command | What it does |
|---|---|
| `qrlab kinds` | Lists every kind with its inputs and parameters. |
| `qrlab validate CONFIG` | Checks the config, the kind, the input files and the parameters, without running. |
| `qrlab run CONFIG` | Runs, writes the outputs and the record. |
| `qrlab run CONFIG --overwrite` | Replaces an existing output folder. |

Exit codes:

- 0: the run succeeded;
- 1: the run failed, and the failure is recorded;
- 2: the config or its inputs were refused before running.

## What a run writes

The output folder holds:

- one CSV file per table;
- one PNG file per figure;
- `report.html`, if the kind writes a report;
- `record.json`, written **last**, so a folder without it is visibly incomplete.

The record contains:

| Field | Content |
|---|---|
| `format` | Version of the record layout ({py:data}`qrlab.experiments.RECORD_FORMAT`, now 1). |
| `experiment`, `config` | Name, kind, hypothesis; the config's path, SHA-256 and full content. |
| `inputs` | Each input as given and as resolved, with its SHA-256 and size. |
| `seed` | The seed, or `null`. |
| `outputs`, `scalars` | Every output file and scalar with its sample tag. |
| `configurations_tried` | How many distinct configs of this experiment have been run so far. |
| `code` | The qrlab version, the git commit and whether the tree was dirty, the Python version and the versions of NumPy, pandas, SciPy, statsmodels and Matplotlib. In the Windows program, the commit comes from the program's build information (`frozen: true`). |
| `started`, `finished`, `status`, `error` | Times in UTC, `success` or `failure`, and the error of a failed run. |

The runner hashes the inputs again after the run. If a file changed during the run, the run
fails.

## The trial ledger

Each run appends a line to `trials.jsonl` in the parent of the output folder.
`configurations_tried` counts the distinct config hashes recorded under the experiment's name.
The config hash covers every table except `[output]`: moving the results is not a new
configuration.

This is the number to report when judging a result. A Sharpe ratio found after trying 40
configurations means less than one found at the first attempt. The deflated Sharpe ratio
({py:func}`qrlab.metrics.deflated_sharpe_ratio`) takes the number of trials as an input.

## Sample tags

Every table and scalar is tagged `in_sample`, `out_of_sample` or `descriptive`. A kind that
fits on the whole history labels its results `in_sample` and says so. Kinds that evaluate
forecasts only on data the forecast never saw, such as the walk-forward backtest and the VaR
backtest, label those results `out_of_sample`.
