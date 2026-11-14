# Experiment kinds

Each kind turns a config into tables, scalars, figures and sometimes a report. The text below
is each kind's own documentation, from its module. `qrlab kinds` lists the same kinds with
their inputs and parameters, and every kind has a runnable example in `configs/experiments/`
or `configs/studies/`.

The kinds' configs are part of the public API (see {doc}`../compatibility`); the modules that
implement them are not.

## General analyses

### `portfolio_report`

*HTML portfolio report with health checks from a broker export (descriptive).*

- Inputs: `transactions`, `transactions_mapping`, `prices`, `prices_mapping`, `instruments`, `checks`; optional: `fx`, `issuers`, `scenarios`, `estr`
- Optional input groups: `extra_prices`, `extra_prices_mapping`, `holdings`, `holdings_mapping`, `tracking`, `tracking_mapping`
- Parameters: `title`, `base_currency`, `language`, `flow_timing`, `max_price_age_days`, `return_frequency`, `generated_at`, `target_weights`; optional: `fx_max_age_days`, `lookthrough_treatment`, `holdings`, `tracking`, `risk`, `projection`
- Seed: not used

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.portfolio_report
   :no-members:
   :no-index:
```

### `risk_report`

*Portfolio risk: covariance, contributions, VaR/ES and a VaR backtest.*

- Inputs: `returns`; optional: none
- Parameters: `returns_format`, `returns_price_type`, `weights`, `covariance`, `confidence`, `periods_per_year`, `filtered`, `backtest`
- Seed: not used

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.risk_report
   :no-members:
   :no-index:
```

### `scenario_analysis`

*Historical and hypothetical stress tests of today's holdings (descriptive).*

- Inputs: `holdings`, `scenarios`; optional: `position_returns`, `factors`, `betas`, `fx`
- Parameters: `as_of`, `value`, `currency`, `csv_format`, `position_returns_currency`, `position_returns_price_type`
- Seed: not used

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.scenario_analysis
   :no-members:
   :no-index:
```

### `projection`

*Monte Carlo projection of a savings or withdrawal plan (descriptive).*

- Inputs: none; optional: none
- Parameters: `assets`, `correlation`, `engine`, `plan`, `flows`, `paths`, `periods`, `start`, `goal_real`, `percentiles`, `early_periods`, `sensitivity`
- Seed: required

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.projection
   :no-members:
   :no-index:
```

### `optimisation`

*Portfolio weights by a construction method, in sample (not a forecast).*

- Inputs: `returns`; optional: none
- Parameters: `returns_format`, `returns_price_type`, `method`, `covariance`, `bounds`, `periods_per_year`
- Seed: not used

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.optimisation
   :no-members:
   :no-index:
```

### `backtest`

*Backtest a named strategy with lag, costs and taxes (gross and net).*

- Inputs: `returns`; optional: none
- Parameters: `returns_format`, `returns_price_type`, `strategy`, `execution_lag`, `policy`, `costs`, `capital_gains_tax`, `initial_weights`, `initial_value`, `currency`, `periods_per_year`
- Seed: not used

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.backtest
   :no-members:
   :no-index:
```

## Studies

The four studies of {doc}`../studies/index`. Their configs are in `configs/studies/`; their
data must be downloaded first (see {doc}`reproducing-studies`).

### `study_volatility_managed`

*Study 1: volatility-managed factors, in sample and in real time after costs.*

- Inputs: `ff3_daily`, `ff3_monthly`, `ff5_daily`, `ff5_monthly`, `mom_daily`, `mom_monthly`; optional: none
- Parameters: `factors`, `start`, `end`, `demean_daily`, `hac_lags`, `burn_in_months`, `leverage_caps`, `costs_bp`, `significance`, `bootstrap`
- Seed: required

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.study_volatility_managed
   :no-members:
   :no-index:
```

### `study_one_over_n`

*Study 2: 1/N against optimised portfolios, out of sample after costs.*

- Inputs: `ind10_daily`, `ind10_monthly`, `p25_daily`, `p25_monthly`, `ff3_monthly`; optional: none
- Parameters: `datasets`, `start`, `end`, `windows`, `strategies`, `costs_bp`, `bl_risk_aversion`, `ceq_risk_aversion`, `hac_lags`, `significance`, `bootstrap`
- Seed: required

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.study_one_over_n
   :no-members:
   :no-index:
```

### `study_factor_zoo`

*Study 3: the factor zoo, multiple testing and post-publication decay.*

- Inputs: `ls_returns`, `signal_doc`; optional: none
- Parameters: `categories`, `end`, `hac_lags`, `min_months`, `hlz_threshold`, `significance`
- Seed: not used

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.study_factor_zoo
   :no-members:
   :no-index:
```

### `study_rebalancing`

*Study 4: rebalancing rules for a EUR ETF investor after costs, tax and FX.*

- Inputs: `kf_developed`, `ecb_fx`, `yc_6y`, `yc_7y`; optional: none
- Parameters: `equity_weight`, `policies`, `reference`, `cost_scenarios`, `tax_rate`, `initial_value`, `end`, `horizon_months`, `n_paths`, `mean_block_length`, `support_share`
- Seed: required

```{eval-rst}
.. automodule:: qrlab.experiments.kinds.study_rebalancing
   :no-members:
   :no-index:
```
