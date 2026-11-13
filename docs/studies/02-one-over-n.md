# Study 2 — 1/N against optimised portfolios

Run on 2026-11-12 with the Ken French data of the same day. The design note was approved before
any result was seen: [`docs/design/5.3-study-2-one-over-n.md`](../design/5.3-study-2-one-over-n.md).

*Research analytics, not investment advice. Past portfolio returns are not a forecast.*

*Re-run on 2026-11-13 from a clean checkout of commit 63f808a, with the same data: every
output was byte-identical.*

## 1. Question and hypotheses

DeMiguel, Garlappi and Uppal (2009) find that none of 14 sample-based optimised portfolios
reliably beats the naive 1/N portfolio out of sample. The extension asks whether methods built
to resist estimation error close that gap:

- Ledoit–Wolf shrinkage;
- risk parity;
- hierarchical risk parity (HRP);
- Black–Litterman (BL), which shrinks sample means toward equilibrium.

The hypotheses were fixed before running:

- **H1 (replication).** No optimised strategy has a significantly higher out-of-sample net
  Sharpe ratio than 1/N. Holm is applied across the 7 strategies, within each dataset, window
  and cost.
- **H2 (robust estimation).** The robust version beats its sample-estimate version in two
  pairs:
  - Ledoit–Wolf minimum variance against sample minimum variance;
  - BL maximum Sharpe against sample maximum Sharpe.

## 2. Data and assumptions

**Universes** (US, USD, value-weighted simple returns, from the Kenneth R. French Data Library):

- **D1:** 10 industry portfolios;
- **D2:** 25 portfolios on size and book-to-market.

**How each series is used:**

- Daily returns drive execution.
- Monthly returns drive estimation.
- Market weights are the number of firms × the average size, lagged one month.
- RF is the monthly one-month T-bill rate from the three-factor file.

**Vintage:** the files were downloaded on 2026-11-12 and stored unchanged in the git-ignored raw
store. They are not redistributed.

| File | Bytes | SHA-256 |
|---|---:|---|
| `10_Industry_Portfolios_CSV.zip` | 118,931 | `cee051709825e60cc38f2aff01c2dec52265aa7ea4a1fefa023a2c8114a5166e` |
| `10_Industry_Portfolios_daily_CSV.zip` | 934,949 | `4c79bad80b6f4eee9d08e649ce223d1c51aadd65043b65baca50b54981d38d25` |
| `25_Portfolios_5x5_CSV.zip` | 549,163 | `ec3a80f94edf98b730790e4fff4f30ed5f0a00494a665c20e15665f580e41557` |
| `25_Portfolios_5x5_Daily_CSV.zip` | 4,043,238 | `820936bd308756c3f66afbb211c9a2a929fed5f8fcf6253fc8a1dfbe2f7c7276` |
| `F-F_Research_Data_Factors_CSV.zip` (RF) | 13,078 | `b03d39e4bb253dda0f14893db3b78e64b40b8d6549a0fc0fd4111dae84c98618` |

**Data checks:**

- No values are missing from 1963-07 to 2026-09.
- Monthly returns compounded from the daily files match the monthly files to within 0.02 %
  per month on average.
- The smallest portfolio has at least 6 firms in every month.

**Samples:** estimation starts in 1963-07. The first decision is at the end of 1973-06, the
first month with a full 120-month window. Every strategy and window is evaluated on the same
months:

- **Main:** 1973-07 to 2026-09 (639 months).
- **Paper period:** 1973-07 to 2004-12 (378 months).

## 3. Specification

The specification was fixed in the design note:

- **Decisions:**
  - made at the last trading day of each month;
  - estimated on a rolling window of the previous $M \in \{60, 120\}$ months of excess returns;
  - all strategies are long-only and fully invested.
- **Execution:**
  - through the backtest engine on daily total returns, one trading day after the decision;
  - every strategy rebalances to its target each month;
  - proportional costs of 0, 10 or 50 bp of the amount traded.
- **Performance:**
  - monthly net returns compounded from the daily ones, minus RF;
  - annualised Sharpe ratio and CEQ ($\gamma=1$);
  - average monthly turnover ($\sum|\text{trades}|/\text{value}$) and maximum drawdown.
- **Strategies:**
  - `ew` (1/N) and `vw` (value weights);
  - `maxsharpe_sample` and `minvar_sample`, from sample moments;
  - `minvar_lw`, minimum variance with the Ledoit–Wolf covariance;
  - `maxsharpe_bl`, maximum Sharpe with the BL posterior. The prior is $\delta=2.5$ times the
    lagged market weights, the views are the window's sample means, and $\tau=1/M$;
  - `risk_parity`, equal risk contributions with the Ledoit–Wolf covariance;
  - `hrp`, with the sample covariance.
- **Fallback:** when no expected excess return is positive, the maximum-Sharpe strategies hold
  minimum variance for that month. In the main run this happened in 4 and 14 months (sample)
  and in 15 and 28 months (BL) with $M=60$, for D1 and D2. With $M=120$ it happened in 1 month
  at most.
- **Tests against 1/N:**
  - Ledoit–Wolf HAC test of the Sharpe-ratio difference (6 lags, primary);
  - Jobson–Korkie–Memmel test, for comparison with the paper;
  - stationary-bootstrap 95 % intervals of the Sharpe and CEQ differences (block 6, 2000
    resamples, seed 20261112).
- **Multiple testing:**
  - Holm across the 7 strategies, within each dataset, window and cost;
  - Holm across the 2 pairs for H2;
  - DSR of the best of the 96 variants per run. The trial ledger records 2 configurations, so
    N = 192.

**Reproduce:**

```bash
uv run qrlab run configs/studies/one_over_n_full.toml
uv run qrlab run configs/studies/one_over_n_paper.toml
```

The configs point at this vintage of the raw files.

## 4. Results (all out of sample)

**How to read the tables:**

- Each cell is the annualised net Sharpe ratio.
- In brackets: the HAC z statistic against 1/N on the same months, then the Holm-adjusted
  p-value.
- 1/N and value weights do not depend on the window.
- Turnover and volatility are shown for $M=120$ at 0 bp.

### Main run, 1973-07 to 2026-09

**D1, 10 industries**

| Strategy | M=60, 0 bp | M=60, 50 bp | M=120, 0 bp | M=120, 50 bp | Turnover/month | Volatility |
|---|---:|---:|---:|---:|---:|---:|
| `ew` | 0.55 | 0.54 | 0.55 | 0.54 | 2.5 % | 15.1 % |
| `vw` | 0.51 (−1.18; 1.00) | 0.50 (−1.25; 0.84) | 0.51 (−1.18; 1.00) | 0.50 (−1.25; 0.84) | 3.2 % | 15.9 % |
| `maxsharpe_sample` | 0.50 (−0.65; 1.00) | 0.40 (−1.75; 0.56) | 0.46 (−1.13; 1.00) | 0.40 (−1.71; 0.51) | 15.4 % | 16.8 % |
| `minvar_sample` | 0.57 (+0.30; 1.00) | 0.52 (−0.21; 1.00) | 0.58 (+0.47; 1.00) | 0.56 (+0.27; 1.00) | 5.1 % | 12.5 % |
| `minvar_lw` | 0.59 (+0.64; 1.00) | 0.55 (+0.16; 1.00) | 0.59 (+0.68; 1.00) | 0.57 (+0.48; 1.00) | 4.8 % | 12.5 % |
| `maxsharpe_bl` | 0.53 (−0.31; 1.00) | 0.45 (−1.38; 0.84) | 0.45 (−1.36; 1.00) | 0.41 (−1.80; 0.50) | 11.0 % | 15.8 % |
| `risk_parity` | 0.57 (+1.81; 0.49) | 0.56 (+1.67; 0.57) | 0.57 (+1.78; 0.52) | 0.56 (+1.72; 0.51) | 2.5 % | 14.3 % |
| `hrp` | 0.59 (+1.80; 0.49) | 0.55 (+0.40; 1.00) | 0.57 (+0.83; 1.00) | 0.54 (+0.10; 1.00) | 6.6 % | 13.7 % |

**D2, 25 size and book-to-market portfolios**

| Strategy | M=60, 0 bp | M=60, 50 bp | M=120, 0 bp | M=120, 50 bp | Turnover/month | Volatility |
|---|---:|---:|---:|---:|---:|---:|
| `ew` | 0.55 | 0.54 | 0.55 | 0.54 | 1.8 % | 18.2 % |
| `vw` | 0.51 (−0.58; 0.86) | 0.50 (−0.70; 1.00) | 0.51 (−0.58; 1.00) | 0.50 (−0.70; 1.00) | 3.3 % | 15.8 % |
| `maxsharpe_sample` | 0.66 (+1.78; 0.38) | 0.56 (+0.19; 1.00) | 0.67 (+1.85; 0.32) | 0.60 (+0.94; 1.00) | 18.9 % | 17.7 % |
| `minvar_sample` | 0.61 (+1.06; 0.86) | 0.55 (+0.22; 1.00) | 0.60 (+0.96; 1.00) | 0.57 (+0.49; 1.00) | 7.7 % | 15.0 % |
| `minvar_lw` | 0.60 (+0.89; 0.86) | 0.55 (+0.22; 1.00) | 0.60 (+0.97; 1.00) | 0.57 (+0.59; 1.00) | 6.5 % | 14.9 % |
| `maxsharpe_bl` | 0.65 (+1.57; 0.47) | 0.57 (+0.44; 1.00) | 0.64 (+1.48; 0.56) | 0.59 (+0.77; 1.00) | 14.4 % | 17.7 % |
| `risk_parity` | 0.56 (+2.19; 0.17) | 0.56 (+2.08; 0.23) | 0.56 (+1.98; 0.28) | 0.55 (+1.93; 0.37) | 1.8 % | 17.7 % |
| `hrp` | 0.58 (+2.41; 0.11) | 0.51 (−2.35; 0.13) | 0.58 (+2.18; 0.20) | 0.52 (−1.37; 1.00) | 14.7 % | 17.2 % |

### Paper period, 1973-07 to 2004-12

**D1, 10 industries**

| Strategy | M=60, 0 bp | M=60, 50 bp | M=120, 0 bp | M=120, 50 bp |
|---|---:|---:|---:|---:|
| `ew` | 0.48 | 0.47 | 0.48 | 0.47 |
| `vw` | 0.41 (−1.77; 0.53) | 0.40 (−1.85; 0.44) | 0.41 (−1.77; 0.53) | 0.40 (−1.85; 0.45) |
| `maxsharpe_sample` | 0.39 (−0.95; 1.00) | 0.29 (−1.86; 0.44) | 0.34 (−1.38; 0.67) | 0.28 (−1.79; 0.45) |
| `minvar_sample` | 0.52 (+0.37; 1.00) | 0.48 (+0.03; 1.00) | 0.51 (+0.27; 1.00) | 0.49 (+0.13; 1.00) |
| `minvar_lw` | 0.53 (+0.59; 1.00) | 0.50 (+0.25; 1.00) | 0.53 (+0.45; 1.00) | 0.50 (+0.30; 1.00) |
| `maxsharpe_bl` | 0.42 (−0.79; 1.00) | 0.33 (−1.69; 0.45) | 0.33 (−1.51; 0.65) | 0.29 (−1.83; 0.45) |
| `risk_parity` | 0.51 (+1.68; 0.56) | 0.50 (+1.56; 0.47) | 0.50 (+1.62; 0.63) | 0.49 (+1.56; 0.48) |
| `hrp` | 0.53 (+1.46; 0.73) | 0.49 (+0.47; 1.00) | 0.51 (+0.86; 1.00) | 0.48 (+0.26; 1.00) |

**D2, 25 size and book-to-market portfolios**

| Strategy | M=60, 0 bp | M=60, 50 bp | M=120, 0 bp | M=120, 50 bp |
|---|---:|---:|---:|---:|
| `ew` | 0.57 | 0.56 | 0.57 | 0.56 |
| `vw` | 0.42 (−2.01; 0.31) | 0.40 (−2.10; 0.25) | 0.42 (−2.01; 0.31) | 0.40 (−2.10; 0.25) |
| `maxsharpe_sample` | 0.67 (+1.35; 0.71) | 0.55 (−0.13; 1.00) | 0.69 (+1.76; 0.47) | 0.62 (+0.76; 1.00) |
| `minvar_sample` | 0.58 (+0.18; 1.00) | 0.52 (−0.59; 1.00) | 0.53 (−0.56; 1.00) | 0.50 (−1.04; 1.00) |
| `minvar_lw` | 0.57 (+0.01; 1.00) | 0.52 (−0.62; 1.00) | 0.54 (−0.49; 1.00) | 0.51 (−0.87; 1.00) |
| `maxsharpe_bl` | 0.65 (+1.23; 0.71) | 0.58 (+0.22; 1.00) | 0.65 (+1.23; 0.79) | 0.60 (+0.61; 1.00) |
| `risk_parity` | 0.59 (+1.63; 0.54) | 0.58 (+1.56; 0.68) | 0.58 (+1.32; 0.79) | 0.58 (+1.28; 1.00) |
| `hrp` | 0.60 (+1.70; 0.54) | 0.53 (−1.58; 0.68) | 0.60 (+1.41; 0.79) | 0.54 (−1.13; 1.00) |

### Multiple testing and selection

- **Main run, against 1/N (H1):**
  - none of the 84 comparisons is significant after Holm, in either direction. The smallest
    adjusted p-value is 0.11 (HRP, D2, $M=60$, 0 bp).
  - Without correction, 8 HAC p-values are below 0.05: risk parity and HRP on D2 (higher than
    1/N), and HRP on D2 at 50 bp (lower than 1/N).
- **Paper period, against 1/N (H1):**
  - nothing is significant after Holm;
  - without correction, only value weights on D2 are significantly *below* 1/N (z ≈ −2.0).
- **CEQ:** the 95 % bootstrap intervals of the CEQ difference against 1/N contain zero in 82 of
  84 comparisons (main run). The exceptions are HRP on D2 at 50 bp, with both windows, where
  1/N is better by 0.6–0.9 % a year. In the paper period they contain zero in 76 of 84. The
  exceptions are value weights on D2 (1/N better by about 3.1 % a year) and HRP on D2 at
  50 bp. These intervals are not corrected for multiple comparisons.
- **Robust pairs (H2):**
  - none of the 24 pair tests per run is significant after Holm. The smallest adjusted
    p-values are 0.10 (main) and 0.33 (paper).
  - The robust version has the higher Sharpe ratio in 13 of 24 cases (main) and 15 of 24
    (paper). On D1, Ledoit–Wolf minimum variance is ahead of sample minimum variance in all 12
    cases (6 per run). The margin is small, 0.01–0.03 in annualised Sharpe ratio, and not
    significant.
- **Deflated Sharpe ratio:**
  - the best variant in both runs is sample maximum Sharpe on D2, $M=120$, 0 bp. Its DSR is
    0.9998 (main) and 0.99 (paper) with N = 192, so its Sharpe ratio is positive beyond what
    selection explains.
  - The DSR tests against **zero**, not against 1/N. Against 1/N the same variant has a Holm
    p-value of 0.32 (main) and 0.47 (paper), and its edge disappears at 50 bp.

## 5. Conclusions

- **H1 is supported: 1/N is not beaten.** No optimised strategy has a significantly higher net
  Sharpe ratio than 1/N, for either universe, window, cost or sample. This agrees with the
  paper's main finding over a further 22 years of data. None is significantly worse after the
  correction either: the honest conclusion is that out-of-sample differences are too noisy to
  rank these strategies.
- **The estimation-error pattern is visible.**
  - **Sample maximum Sharpe on D1:** its Sharpe ratio is below 1/N's in every cell (0.40–0.50
    against 0.55), only BL maximum Sharpe is as low, and it has 6–11 times the turnover of
    1/N.
  - **Sample maximum Sharpe on D2:** it has the highest point estimates (0.66–0.69). These fall
    to 0.55–0.62 at 50 bp and are not significant.
  - **Minimum variance:** it lowers volatility (12.5 % against 15.1 % on D1) without raising the
    Sharpe ratio. Its CEQ is lower than 1/N's, because with $\gamma=1$ the lower mean outweighs
    the lower variance.
- **H2 is not supported.** Neither shrinkage nor Black–Litterman significantly improves on its
  sample-estimate version; the signs are close to a coin flip. Ledoit–Wolf gives a small,
  consistent but insignificant edge for minimum variance on the 10 industries.
- **Risk parity and HRP** are the closest to 1/N, with similar Sharpe ratios. Risk parity has
  the same low turnover. Their unadjusted edges on D2 do not survive the correction across
  strategies.

## 6. Limitations

- **Costs:**
  - A flat proportional cost understates the cost of trading the small-firm portfolios of D2,
    which the optimisers often favour.
  - Fixed costs, market impact and short-sale constraints of real funds are not modelled.
- **The portfolios are not investable.** They are paper portfolios.
- **Differences from the paper:**
  - the datasets differ: DGU add the market and also use other datasets;
  - execution is one trading day after the decision, where DGU use no lag;
  - only long-only versions are evaluated; the unconstrained sample tangency portfolio is not.
- **Fixed settings:** the BL settings ($\delta=2.5$, $\tau=1/M$, sample-mean views) and the
  6-lag HAC were fixed in advance and not tuned. Other choices could change the BL results.
- **Fallback months:** with $M=60$ the maximum-Sharpe strategies held minimum variance in up
  to 28 of 639 months. They are part of the reported strategy, not removed.
- **Data revisions:** the Ken French library revises history. Results depend on this vintage
  (hashes above).

## References

- DeMiguel, V., Garlappi, L. and Uppal, R. (2009). Optimal versus naive diversification: how
  inefficient is the 1/N portfolio strategy? *Review of Financial Studies* 22(5).
- Ledoit, O. and Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance
  matrices. *Journal of Multivariate Analysis* 88(2).
- Ledoit, O. and Wolf, M. (2008). Robust performance hypothesis testing with the Sharpe ratio.
  *Journal of Empirical Finance* 15(5).
- López de Prado, M. (2016). Building diversified portfolios that outperform out of sample.
  *Journal of Portfolio Management* 42(4).
- Black, F. and Litterman, R. (1992). Global portfolio optimization. *Financial Analysts
  Journal* 48(5).
- Bailey, D. H. and López de Prado, M. (2014). The deflated Sharpe ratio. *Journal of Portfolio
  Management* 40(5).
