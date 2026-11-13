# Introduction

Many portfolio rules are first established in sample: a regression on the full history, a
backtest whose parameters were chosen with that history in view, a predictor reported because
it was significant. Investors face a different problem. They must:

- estimate in real time from the past alone;
- pay to trade, and in many countries pay tax on realised gains;
- read published results that are the survivors of many tests.

This paper asks what survives when four well-known portfolio rules are put through those
conditions.

The four studies are deliberately different:

- **Study 1** revisits volatility-managed factors (Moreira and Muir, 2017). It asks whether
  their in-sample alphas survive real-time scaling and costs, as Cederburg, O'Doherty, Wang and
  Yan (2020) argue they do not.
- **Study 2** repeats the comparison of DeMiguel, Garlappi and Uppal (2009) between naive 1/N
  diversification and optimised portfolios, on a longer sample and after costs.
- **Study 3** takes the published cross-sectional predictors collected by Chen and Zimmermann
  (2022). It asks how many pass a multiple-testing bar (Harvey, Liu and Zhu, 2016) and how much
  their returns fall after the original sample and after publication (McLean and Pontiff, 2016).
- **Study 4** asks a practical question for a euro-area investor holding equity and bond ETFs:
  how often to rebalance when every sale of a winner is taxed at 26 %.

What they share is a method. Each began with a design note, approved before any result was
seen, which fixes the hypotheses, the data, the tests and the families over which tests are
corrected (see Methods). Each was run as a config through the same experiment runner. The runner
records the data hashes, the code version and the number of configurations tried, and tags
every result as in-sample, out-of-sample or descriptive. The paper reports what was
pre-specified, including the hypotheses that failed.

## Main findings

- **Study 1.** Volatility management gives significant in-sample alphas for several factors.
  For the market the alpha is {{ s1_mkt_alpha }} a year, with a t-statistic of
  {{ s1_mkt_alpha_t }}.
  - In real time and after costs, it does not raise the Sharpe ratio of any factor except
    momentum, and it lowers it for some.
  - Momentum is the exception. With a leverage cap, the managed version has a net Sharpe ratio
    of {{ s1_mom5_sr0 }} against {{ s1_mom_sr }} for momentum itself. The gain survives the Holm
    correction within its family and has a deflated Sharpe probability of {{ s1_dsr }}. The
    evidence is moderate, not decisive.
- **Study 2.** No optimised strategy has a significantly higher net Sharpe ratio than 1/N, in
  any of the universes, estimation windows or cost levels tested from {{ s2_main_start }} to
  {{ s2_main_end }}. None is significantly worse after correction either: out-of-sample
  differences are too noisy to rank these strategies.
- **Study 3.** {{ s3_is_single_share }} of {{ s3_n_clear }} "clear" predictors pass a single
  test in their original samples. The share falls under stricter bars:
  - {{ s3_is_t3_share }} under t > 3;
  - {{ s3_is_holm_share }} under Holm;
  - {{ s3_is_by_share }} under the Benjamini-Yekutieli correction.

  A panel regression with predictor fixed effects finds returns {{ s3_decay_ps_round }} lower
  after the original sample and {{ s3_decay_pp_round }} lower after publication. They are
  smaller, but still positive.
- **Study 4.** Rebalancing every month costs a median {{ s4_s_monthly_diff }} of after-tax
  wealth over 20 years against annual rebalancing. It loses in {{ s4_h2 }} of simulated paths
  and barely changes volatility.
  - Buy-and-hold ends richer in {{ s4_h3_wealth }} of paths. It does so by drifting towards
    equity, so in effect it becomes a different and riskier portfolio.
  - A 5-point tolerance band trades far less than quarterly rebalancing, and behaves much like
    annual rebalancing.

## Contribution

The contribution is not a new anomaly or a new estimator. It has three parts:

- **Updated replications** of three well-known results, on data that extend to {{ s1_end }}.
- **One pre-specified, multiple-testing-aware framework** applied to four questions, with the
  number of configurations tried reported for each.
- **A study written for a specific, realistic investor:** euro-area, taxed, holding ETFs.

Everything is reproducible:

- the library, the configs and the design notes are public;
- each result in this paper is generated from the run records, so the text cannot drift from
  the numbers;
- the data files are identified by their hashes (Appendix A).

## Structure of the paper

- **Methods** describes what the four studies share.
- **Four sections**, one per study, present the studies.
- **Discussion** looks at what they have in common.
- **Limitations** gathers the limits.
- **Conclusion** closes the paper.

Throughout, results are research analytics on historical and simulated data. They are not
forecasts and not investment advice.
