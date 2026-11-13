# A first run

Every analysis in Quant Research Lab is a **config**: a TOML file that names an experiment kind,
its input files and its parameters. The same runner executes it from the command line, from
Python or from the desktop app, and writes the same outputs and the same `record.json`.

The repository ships one example config per general kind in `configs/experiments/`. They run on
the synthetic files in `examples/data/`.

## From the command line

```bash
uv run qrlab kinds
uv run qrlab validate configs/experiments/example_risk_report.toml
uv run qrlab run configs/experiments/example_risk_report.toml
```

`validate` checks the config, its inputs and its parameters without running anything. `run`
writes into the folder named in the config's `[output]` table, here
`results/example-risk-report/`:

- one CSV file per table;
- one PNG file per figure;
- an HTML report, if the kind writes one;
- `record.json`.

## From Python

The same run, through the public API:

```{doctest}
>>> from pathlib import Path
>>> from qrlab.experiments import run_experiment
>>> from qrlab.experiments.kinds import KINDS
>>> result = run_experiment(
...     Path("configs/experiments/example_risk_report.toml"), kinds=KINDS, overwrite=True
... )
>>> result.succeeded
True
>>> sorted(result.record["outputs"])
['contributions.csv', 'covariance.csv', 'var_backtest.csv', 'var_es.csv']
>>> volatility = result.record["scalars"]["volatility_annual"]
>>> round(volatility["value"], 4), volatility["tag"]
(0.0818, 'descriptive')
```

Every table and scalar carries a **sample tag**:

- `in_sample`: fitted on the data it is evaluated on;
- `out_of_sample`: evaluated on data the estimate never saw;
- `descriptive`: a description of the data, not an estimate to be tested.

The tag travels with the number into the record, the reports and the app.

## A portfolio X-ray

`configs/experiments/example_portfolio_report.toml` turns a synthetic broker export into an
HTML report. Its sections are:

- a summary with time- and money-weighted returns, labelled and never mixed;
- positions and cash;
- a breakdown of the result into its sources;
- income and costs;
- charts;
- look-through exposures;
- risk and stress tests;
- a projection;
- the health checks;
- the data and assumptions used.

The example is in Italian; `language` is a parameter of the config.

```bash
uv run qrlab run configs/experiments/example_portfolio_report.toml
```

To use your own portfolio:

1. Copy the example config and its mapping files into the git-ignored `data/` folder.
2. Point `[inputs]` at your files.
3. Run the copy.

Real portfolio data never belongs anywhere else in the repository.

## What next

- {doc}`../guides/experiments`: the config format, the record and the trial ledger.
- {doc}`../guides/kinds`: what each experiment kind computes and its parameters.
- {doc}`../guides/desktop-app`: the same analyses without the command line.
