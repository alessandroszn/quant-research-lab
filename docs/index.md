# Quant Research Lab

`qrlab` is a Python framework for quantitative financial research, portfolio analytics and
backtesting, with a Windows desktop app on top of the same library. Correctness,
reproducibility and methodological rigour come before speed or feature count.

It has three pillars:

- **Portfolio and ETF analytics.** Time- and money-weighted performance, risk, look-through
  exposures, health checks, stress tests and projections.
- **A research lab.** Optimisation, look-ahead-free backtests, attribution and four
  reproducible studies on public data.
- **A desktop app.** The same analyses without the command line, with no financial logic of
  its own.

Every analysis is a config run by one experiment runner. It records its inputs, code version
and the number of configurations tried, and labels every result as in-sample, out-of-sample or
descriptive.

Everything here is research analytics, not investment advice.

```{toctree}
:maxdepth: 2
:caption: Getting started

getting-started/installation
getting-started/first-run
```

```{toctree}
:maxdepth: 2
:caption: Guides

guides/experiments
guides/kinds
guides/desktop-app
guides/reproducing-studies
guides/data-sources
```

```{toctree}
:maxdepth: 2
:caption: Methodology

methodology/index
```

```{toctree}
:maxdepth: 1
:caption: Studies

studies/index
```

```{toctree}
:maxdepth: 1
:caption: Working paper

paper/index
```

```{toctree}
:maxdepth: 2
:caption: Reference

reference/index
compatibility
```

```{toctree}
:maxdepth: 1
:caption: Project

project/changelog
project/releasing
ARCHITECTURE
ROADMAP
IDEAS
project/design-notes
```
