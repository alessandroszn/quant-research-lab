# Study 2: 1/N against optimised portfolios

## Question and hypotheses

DeMiguel, Garlappi and Uppal (2009), hereafter DGU, compare 14 sample-based optimised
portfolios with the naive 1/N portfolio. None of them reliably beats 1/N out of sample. Their
explanation is estimation error: the sample means and covariances that feed the optimiser are
too noisy for the gains of optimisation to show up in realised returns.

This study replicates that comparison on a longer sample and extends it. The extension asks
whether methods built to resist estimation error close the gap. Four such methods are tested:
Ledoit–Wolf shrinkage of the covariance matrix (Ledoit and Wolf, 2004), risk parity,
hierarchical risk parity (HRP; López de Prado, 2016), and Black–Litterman (BL; Black and
Litterman, 1992), which shrinks sample means toward equilibrium returns.

Two hypotheses were fixed in the design note before any result was seen:

- **H1 (replication).** No optimised strategy has a significantly higher out-of-sample net
  Sharpe ratio than 1/N. The Holm correction is applied across the 7 strategies compared with
  1/N, within each universe, window and cost.
- **H2 (robust estimation).** The robust version of a strategy beats its sample-estimate
  version. Two pairs are tested: Ledoit–Wolf minimum variance against sample minimum variance,
  and BL maximum Sharpe against sample maximum Sharpe. Holm is applied across the 2 pairs.

An honest null result counts as a result. For H1 the null is the expected outcome; for H2 it is
not.

## Data and specification

**Universes.** Both come from the Kenneth R. French Data Library: US stocks, USD,
value-weighted simple returns.

- **D1** (`industries_10` in the tables): 10 industry portfolios.
- **D2** (`size_bm_25`): 25 portfolios formed on size and book-to-market.

Daily returns drive execution and monthly returns drive estimation. Market weights, used by
value weights and by the BL prior, are the number of firms times the average firm size, lagged
one month. The risk-free rate is the one-month T-bill rate from the three-factor file. The raw
files are stored unchanged with their hashes and are not redistributed. The data checks found
no missing values over the sample, a close match between monthly returns compounded from the
daily files and the monthly files, and no portfolio without firms in any month.

**Samples.** Estimation data start in 1963-07. The first decision is the first month-end with a
full 120-month window. Every strategy and window is evaluated on the same months:

- **main run:** {{ s2_main_start }} to {{ s2_main_end }}, {{ s2_main_n }} months;
- **paper period:** {{ s2_paper_start }} to {{ s2_paper_end }}, {{ s2_paper_n }} months, which
  ends where DGU's sample ends.

**Timing and execution.** Decisions are made on the last trading day of each month. They use
only the monthly excess returns of the previous $M$ months, on a rolling window with
$M \in \{60, 120\}$. All strategies are long-only and fully invested, and each rebalances to its
target every month. Trades go through the backtest engine on daily total returns, one trading
day after the decision. DGU use no lag; one trading day is the smallest lag the project allows.
Proportional costs are 0, 10 or 50 bp of the amount traded; 50 bp is DGU's cost.

**Strategies.** Eight strategies are run:

- `ew`: 1/N, the benchmark;
- `vw`: value weights, which is also the BL prior without views;
- `maxsharpe_sample` and `minvar_sample`: maximum Sharpe ratio and minimum variance from the
  sample moments;
- `minvar_lw`: minimum variance with the Ledoit–Wolf covariance;
- `maxsharpe_bl`: maximum Sharpe ratio with the BL posterior. The prior is $\delta = 2.5$
  times the covariance times the lagged market weights. The views are the window's sample
  means, with $\tau = 1/M$;
- `risk_parity`: equal risk contributions with the Ledoit–Wolf covariance;
- `hrp`: HRP with the sample covariance.

When no expected excess return is positive, a maximum-Sharpe portfolio is not defined, and the
strategy holds minimum variance for that month. In the main run with $M = 60$, this happened in
{{ s2_fb_sample_d1 }} and {{ s2_fb_sample_d2 }} months for the sample version (D1 and D2) and
in {{ s2_fb_bl_d1 }} and {{ s2_fb_bl_d2 }} months for the BL version. With $M = 120$ it happened
in {{ s2_fb_bl_d1_120 }} month at most. These months are part of the reported strategy; they
are not removed.

**Performance and tests.** Monthly net returns are compounded from the daily net returns, and
the monthly risk-free rate is subtracted. The study reports the annualised mean, volatility and
Sharpe ratio, the certainty-equivalent return $\text{CEQ} = 12(\hat\mu - \tfrac{\gamma}{2}
\hat\sigma^2)$ with $\gamma = 1$, average monthly turnover and maximum drawdown. Each strategy
is compared with 1/N on the same months by the Ledoit and Wolf (2008) HAC test of the
Sharpe-ratio difference, with 6 lags; this is the primary test. The Jobson–Korkie–Memmel test
is also reported, for comparison with DGU. Stationary-bootstrap 95 % intervals (mean block 6,
2,000 resamples, fixed seed) cover the Sharpe and CEQ differences.

**Multiple testing.** Holm is applied as stated in the hypotheses. Each run has 96 variants
(2 universes × 2 windows × 3 costs × 8 strategies). The best variant gets a deflated Sharpe
ratio (DSR; Bailey and López de Prado, 2014). The trial ledger records
{{ s2_configs_tried }} configurations (the main run and the paper period), so the DSR uses
N = {{ s2_dsr_trials }} trials.

## In-sample results

There are none to report: every weight is estimated on data that end before the decision, and
every result below is out of sample by construction.

## Out-of-sample results

Table 2.1 shows the main run with $M = 120$ at 50 bp, DGU's cost. Every figure is annualised
and net of costs, except turnover, which is the average monthly amount traded as a share of
portfolio value.

**Table 2.1.** Main run, {{ s2_main_start }} to {{ s2_main_end }}, $M = 120$, 50 bp: net
performance.

```{include} _generated/s2_performance.md
```

**1/N.** On D1, 1/N has a Sharpe ratio of {{ s2_d1_ew_sharpe }} without costs and
{{ s2_d1_ew_sharpe_50 }} at 50 bp. Its volatility is {{ s2_d1_ew_vol }} and its monthly
turnover {{ s2_d1_ew_turnover }}. On D2 its Sharpe ratio without costs is
{{ s2_d2_ew_sharpe }}, with turnover of {{ s2_d2_ew_turnover }}. 1/N and value weights do not
depend on the window.

**Sample maximum Sharpe.** This strategy shows the estimation-error pattern most clearly. On D1
its Sharpe ratio ranges from {{ s2_d1_mss_sharpe_60 }} ($M = 60$, 0 bp) down to
{{ s2_d1_mss_sharpe_120_50 }} ($M = 120$, 50 bp), below 1/N in every cell. Only BL maximum
Sharpe is comparably low. Its monthly
turnover is {{ s2_d1_mss_turnover_60 }} with $M = 60$ and {{ s2_d1_mss_turnover }} with
$M = 120$, many times that of 1/N. On D2 the same strategy has the highest point estimates of
the study: {{ s2_d2_mss_sharpe_60 }} and {{ s2_d2_mss_sharpe_120 }} without costs, for the two
windows. At 50 bp these fall to {{ s2_d2_mss_sharpe_60_50 }} and
{{ s2_d2_mss_sharpe_120_50 }}, because its turnover is {{ s2_d2_mss_turnover }} a month.

**Minimum variance.** Both minimum-variance versions lower volatility without raising the
Sharpe ratio much. On D1 sample minimum variance has volatility of {{ s2_d1_mvs_vol }}, against
{{ s2_d1_ew_vol }} for 1/N. Its Sharpe ratio without costs is {{ s2_d1_mvs_sharpe }}, and
{{ s2_d1_mvlw_sharpe }} with the Ledoit–Wolf covariance. Its CEQ is lower than that of 1/N,
{{ s2_d1_mvs_ceq }} against {{ s2_d1_ew_ceq }}: with $\gamma = 1$ the lower mean outweighs the
lower variance.

**Black–Litterman.** BL maximum Sharpe behaves much like its sample version. On D1 with
$M = 120$ and no costs its Sharpe ratio is {{ s2_d1_bl_sharpe }}, against {{ s2_d1_ew_sharpe }}
for 1/N. On D2 its point estimates are high but, like those of the sample version, not
significant.

**Risk parity and HRP.** These are the closest to 1/N, with similar Sharpe ratios. Risk parity
also has the same low turnover as 1/N: {{ s2_d1_rp_turnover }} on D1 and {{ s2_d2_rp_turnover }}
on D2. HRP trades more, especially on D2, and loses more to costs.

## Statistical and economic significance

Table 2.2 gives the tests against 1/N for the same cells as Table 2.1. HAC z and its p-value
test the Sharpe-ratio difference; the Holm p-value is adjusted across the 7 strategies. ΔCEQ is
the annual CEQ difference with its 95 % bootstrap interval; a negative value means 1/N is
better.

**Table 2.2.** Main run, $M = 120$, 50 bp: tests against 1/N.

```{include} _generated/s2_tests.md
```

**H1, main run.** There are 84 comparisons with 1/N (7 strategies × 2 universes × 2 windows ×
3 costs). After the Holm correction, the number significantly better than 1/N is
{{ s2_better_main }}, and the number significantly worse is {{ s2_worse_main }}. The smallest adjusted p-value is
{{ s2_min_holm }}, for HRP on D2 with $M = 60$ and no costs (HAC z = {{ s2_min_holm_z }}).
Without the correction, a few HAC p-values fall below 0.05, all on D2. Risk parity and HRP are
above 1/N, for example risk parity with $M = 60$ and no costs (z = {{ s2_rp_d2_z }}, Holm p =
{{ s2_rp_d2_holm }}). HRP at 50 bp with $M = 60$ is below 1/N (z = {{ s2_hrp_d2_50_z }}, Holm p
= {{ s2_hrp_d2_50_holm }}). None survives the correction across strategies.

**H1, paper period.** After Holm, the number of comparisons significantly better than 1/N is
{{ s2_better_paper }}, and the number significantly worse is {{ s2_worse_paper }}. Without correction, only value weights on
D2 are below 1/N, in the opposite direction to the optimisers: z runs from
{{ s2_paper_vw_z_0 }} at 0 bp to {{ s2_paper_vw_z_50 }} at 50 bp, with a Holm p-value of
{{ s2_paper_vw_holm_50 }} at best.

**Economic size.** The bootstrap intervals of the CEQ difference contain zero in most cells of
the main run. The exceptions are HRP on D2 at 50 bp, with both windows: 1/N is better by
{{ s2_hrp_d2_50_ceq_60 }} a year with $M = 60$ and by {{ s2_hrp_d2_50_ceq_120 }} with
$M = 120$. In the paper period the exceptions are the same HRP cells and value weights on D2,
where 1/N is better by {{ s2_paper_vw_ceq_0 }} to {{ s2_paper_vw_ceq_50 }} a year. These
intervals are not corrected for multiple comparisons.

**H2.** Each run has 24 pair tests (2 pairs × 2 universes × 2 windows × 3 costs). The number
in which the robust version is significantly better after Holm is {{ s2_robust_better_main }}
in the main run and {{ s2_robust_better_paper }} in the paper period. The smallest adjusted p-values are {{ s2_pair_min_holm_main }}
(main run; Ledoit–Wolf minimum variance on D1, $M = 60$, 50 bp, z = {{ s2_pair_min_z_main }})
and {{ s2_pair_min_holm_paper }} (paper period). The robust version has the higher Sharpe ratio
in about half of the cases, close to a coin flip. The one consistent sign is on D1, where
Ledoit–Wolf minimum variance is ahead of sample minimum variance in every cell of both runs.
The margin is small and not significant.

**Deflated Sharpe ratio.** The best variant in both runs is sample maximum Sharpe on D2 with
$M = 120$ and no costs. Its DSR is {{ s2_dsr_main }} in the main run and {{ s2_dsr_paper }} in
the paper period, with N = {{ s2_dsr_trials }}. Its Sharpe ratio is therefore positive beyond
what selection among the trials explains. The DSR tests against zero, not against 1/N. Against
1/N the same variant has a Holm p-value of {{ s2_dsr_holm_main }} (main) and
{{ s2_dsr_holm_paper }} (paper period), and its edge over 1/N largely disappears at 50 bp.

**Verdict.** H1 is supported: 1/N is not beaten, for either universe, window, cost or sample.
This agrees with DGU on a longer sample. No strategy is significantly worse after the
correction either. The honest reading is that out-of-sample differences are too noisy to rank
these strategies. H2 is not supported: neither shrinkage nor BL significantly improves on its
sample-estimate version.

## Robustness

The design fixes the robustness checks in advance, and every one is reported in the full
report.

- **Sample.** The paper period, which ends where DGU's sample ends, gives the same verdict on
  both hypotheses. On D1, 1/N has a Sharpe ratio of {{ s2_paper_d1_ew_sharpe }} without costs,
  and sample maximum Sharpe falls to {{ s2_paper_d1_mss_sharpe_50 }} with $M = 120$ at 50 bp.
  On D2 sample maximum Sharpe again has the highest point estimate,
  {{ s2_paper_d2_mss_sharpe }} with $M = 120$ and no costs, and {{ s2_paper_d2_mss_sharpe_50 }}
  at 50 bp; it is not significant.
- **Window.** Results with $M = 60$ and $M = 120$ lead to the same conclusions. The shorter
  window raises the turnover of the maximum-Sharpe strategies and the number of fallback months.
- **Costs.** At 0, 10 and 50 bp no strategy beats 1/N after the correction. Costs mostly hurt
  the high-turnover strategies: sample and BL maximum Sharpe, and HRP on D2.
- **Test.** The Jobson–Korkie–Memmel statistics are reported next to the HAC ones in
  Table 2.2, for comparison with DGU.
- **Settings not varied.** The BL settings ($\delta = 2.5$, $\tau = 1/M$, sample-mean views)
  and the 6-lag HAC were fixed in advance and not tuned. Other choices could change the BL
  results.

Three limits apply to all of these checks. A flat proportional cost understates the cost of
trading the small-firm portfolios of D2, which the optimisers often favour. The portfolios are
paper portfolios, not investable funds. The universes, the one-day lag and the long-only
constraint differ from DGU, so the replication is close but not exact. These results are
research analytics, not investment advice.

The [full report](../studies/02-one-over-n.md) gives every cell, both runs and the complete
data provenance.
