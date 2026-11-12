"""Empirical studies built on the library (phase 5.3).

Each study is a module of pure functions, tested on synthetic data, and an experiment kind in
:mod:`qrlab.experiments.kinds` that runs it on real data through the same runner as every other
analysis. Studies keep data, specification, in-sample and out-of-sample results and statistical
and economic significance apart.

- ``volatility_managed``: study 1, volatility-managed factors (Moreira and Muir 2017) and their
  real-time implementability (Cederburg, O'Doherty, Wang and Yan 2020).
"""
