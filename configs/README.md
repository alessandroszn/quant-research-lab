# configs/

Experiment configurations (one file per experiment). Configuration is kept separate from code:
parameters, date ranges, universes and cost assumptions live here, never hardcoded in modules.
No credentials or machine-specific paths belong in these files.

`experiments/` holds runnable example experiments on the synthetic files in `examples/data/`:

```bash
uv run qrlab kinds
uv run qrlab validate configs/experiments/example_backtest.toml
uv run qrlab run configs/experiments/example_backtest.toml
```

Each run writes its outputs and a `record.json` under `results/` (git-ignored). The record holds
the config, input hashes, the code version and the number of configurations tried. For your own
data, copy an example, point `[inputs]` at files under `data/` (git-ignored) and keep the copy
there too.

`studies/` holds the configs of the published studies (`docs/studies/`). Their inputs are raw
files in the git-ignored `data/raw/` store: download the same datasets first (see the study's
report for the files and their SHA-256), and update the paths if your vintage differs.
