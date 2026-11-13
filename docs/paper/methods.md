# Methods common to the four studies

The four studies share one way of working. This section describes it once. The specifics of each
study (samples, parameters, families of tests) are in its own section and report.

## Pre-specification

Each study began with a design note, approved before any result was seen. The note fixes:

- the questions and hypotheses;
- the data;
- the estimators and tests;
- the families over which multiple-testing corrections apply;
- the robustness checks.

The notes are in `docs/design/5.3-study-*.md`. Where the data forced a change (for example a
predictor category that the specification did not foresee), the change was decided before
looking at the affected results and is recorded at the end of the note as a deviation.

## Data and provenance

All data are public. Raw files are downloaded once and stored unchanged in a local raw store,
with their source, URL, download time, size, SHA-256 and terms of use. Parsers are strict: dates,
separators, units and missing-value codes are declared, never guessed, and an unknown format
raises. Returns are simple returns. The number of periods per year is always an explicit
parameter, and excess returns subtract the risk-free rate of the same period. Appendix A lists
the exact files used, with their hashes.

## One runner, one record per run

Each study is an experiment kind of the Quant Research Lab library, run from a config file by
the same runner used for every other analysis. The runner validates the config and hashes every
input. It then runs the study and writes:

- every table as CSV, every figure as PNG, the report as HTML;
- a `record.json` with the config, the input hashes, the code version, the number of
  configurations tried and a **sample tag** on every output.

The tags are `in_sample`, `out_of_sample` and `descriptive`. In-sample estimates and real-time or
out-of-sample results are kept in separate tables and never mixed in one number.

Each run also appends a line to a **trial ledger**. "Configurations tried" is the number of
distinct configs run under a study's name: the main specification and every robustness config.
This is the number reported in Appendix A, and it enters the deflated Sharpe ratios below. It is
the honest count of what was tried through the runner. Exploration outside the runner would not
be counted, and the studies were not explored outside it.

## Inference

- **Regressions.** Spanning regressions and the decay regression of study 3 use Newey and West
  (1987) standard errors. The panel regression of study 3 has predictor fixed effects and errors
  clustered by month.
- **Comparing Sharpe ratios.** Differences between two strategies' Sharpe ratios are tested in
  three ways:
  - with a HAC standard error;
  - with the Jobson and Korkie (1981) test as corrected by Memmel (2003), for comparison with
    earlier work;
  - with a stationary bootstrap interval (Politis and Romano, 1994), in the spirit of Ledoit and
    Wolf (2008).

  The bootstrap resamples the joint returns in blocks, so autocorrelation and cross-correlation
  are kept.
- **Multiple testing.** Within each pre-specified family of comparisons, p-values are adjusted
  with:
  - Holm (1979), which controls the family-wise error rate;
  - Benjamini and Hochberg (1995), which controls the false discovery rate.

  Study 3 adds the Benjamini and Yekutieli (2001) correction, valid under any dependence, and
  the t > 3 threshold of Harvey, Liu and Zhu (2016). A result is called significant only if it
  survives the correction stated for its family.
- **Selection.** Where a study picks the best of several variants, the deflated Sharpe ratio of
  Bailey and López de Prado (2014) measures the chance that the best variant beats zero after
  the search. Its number of trials is the variants in the run multiplied by the configurations
  tried.
- **Economic significance.** It is reported next to statistical significance and never replaced
  by it. The measures are differences in annual Sharpe ratio and certainty-equivalent return, and
  differences in euros of wealth after costs and tax.

## Costs, taxes and timing

- **Execution lag.** Every decision uses only data available at the time and is executed in a
  later period. The backtests use the same execution lag throughout.
- **Real-time estimation.** Quantities that a real-time investor would have to estimate, such as
  the scaling constants of study 1 or the covariance matrices of study 2, are estimated on past
  data only.
- **Costs and taxes.** Trading costs are proportional to the amount traded, with the scenarios
  fixed in the design notes. Study 4 applies Italian taxation of realised capital gains, without
  offsetting losses.
- **Gross and net.** Gross and net results are reported side by side; study 3 is the exception,
  because the Open Source Asset Pricing returns are gross.

## Reproduction

Every table and number in this paper is read from the run records by a script, so the paper
cannot drift from the results it reports. Appendix A gives:

- the code version and commit of each study;
- the data files and their hashes;
- the command that reruns each study.
