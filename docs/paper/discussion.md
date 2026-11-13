# Discussion

The four studies ask different questions, yet their answers share a pattern. What looks good in
sample depends on information, trading or a search that a real investor does not have for free.
Once those are paid for, most of the advantage is gone. What survives is narrow and specific.

## Estimation error decides most comparisons

Studies 1 and 2 are both about estimation:

- the scaling constant and the variance forecast of a volatility-managed factor;
- the means and covariances behind an optimised portfolio.

In sample, these quantities are known with hindsight, and the rules built on them look better.
In real time they must be estimated. The estimation error then shows up as extra turnover,
extreme weights and fallback months, and it cancels most of the benefit. Study 2's sample
maximum-Sharpe portfolio is the clearest case. It trades many times more than 1/N, has a lower
Sharpe ratio on the industry portfolios, and its best results elsewhere are not significant.
1/N wins not because it is optimal but because it has nothing to estimate.

## Frictions are first-order

Costs and taxes are not details:

- in study 1, trading costs of 25 bp are enough to make some managed factors
  significantly *worse* than the plain factor;
- in study 4, the tax on realised gains, not trading costs, makes frequent rebalancing
  expensive. Monthly rebalancing loses {{ s4_s_monthly_diff }} of median after-tax wealth
  against annual rebalancing over 20 years, while volatility barely changes.

A rule that is evaluated without its frictions answers a different question from the one an
investor faces.

## Publication and the number of tests

Study 3 measures what the first two take for granted: a published result is a selected result.

- Most published predictors pass a single test in their own sample, as one would expect of
  results chosen for being significant.
- Under bars that account for the number of tests, a sizeable minority would not have been
  reported.
- After publication, returns are {{ s3_decay_pp_round }} lower.

The trial ledger of the experiment runner applies the same logic to this paper. Each study
reports how many configurations were tried, and the deflated Sharpe ratios of studies 1 and 2
are computed with that count.

## Why the null results matter

Two of the four headline hypotheses predicted a null result: that implementable volatility
management and optimised portfolios do not beat their simple counterparts. In both cases the
null was not rejected for most strategies. With the sample sizes available, "not significantly
different" is the honest conclusion, and it is informative. It says that any advantage of the
more complex rule is too small, relative to the noise, to be relied on. Reporting these null
results, rather than searching for a specification that rejects, is what the pre-specified
design notes are for.

## What survives

Two things survive the frictions and the multiple-testing bars:

- **Momentum timing.** Scaling momentum by its recent volatility improves its real-time net
  Sharpe ratio, with a moderate strength of evidence, in line with Barroso and Santa-Clara
  (2015).
- **Simple rules that trade rarely.** Annual rebalancing, or a wide tolerance band, keeps a
  taxed portfolio close to its target at a small cost.

Neither is new. That the survivors are the simplest and best-documented rules is itself the
finding.
