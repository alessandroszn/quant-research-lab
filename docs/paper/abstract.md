# Abstract

Four portfolio rules that look good in sample are examined under the conditions an investor
actually faces: real-time estimation, trading costs, taxes and the number of tests behind a
published result. Each study was specified before any result was seen and run through one
experiment runner, which records its data, code and the configurations tried.

- **Volatility-managed factors** produce significant in-sample alphas, for example
  {{ s1_mkt_alpha }} a year for the market. In real time, after costs, they improve the Sharpe
  ratio only for momentum ({{ s1_mom5_sr0 }} against {{ s1_mom_sr }}).
- **Optimised portfolios.** None of seven optimised portfolios has a significantly higher net
  Sharpe ratio than 1/N.
- **Published equity predictors.** {{ s3_is_single_share }} of {{ s3_n_clear }} pass a single
  test in their original samples, but only {{ s3_is_holm_share }} survive a Holm correction.
  Their returns are {{ s3_decay_ps_round }} lower after the sample and {{ s3_decay_pp_round }}
  lower after publication.
- **Rebalancing for a EUR ETF investor under Italian capital-gains tax.** Monthly rebalancing
  costs a median {{ s4_s_monthly_diff }} over 20 years against annual rebalancing, and buys
  almost no risk control.

What survives is narrow: momentum timing, and simple rules that trade rarely. The code, configs
and records are public, and every number in this paper is generated from the run records.

**Keywords:** volatility management, 1/N, factor zoo, multiple testing, rebalancing,
reproducibility.
**JEL:** G11, G12, G14, C12, C58.
