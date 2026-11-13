# Study 1 — Volatility-managed factors: in sample and in real time

Run on 2026-11-12 with the Ken French data of the same day. The design note was approved before
any result was seen: [`docs/design/5.3-study-1-volatility-managed.md`](../design/5.3-study-1-volatility-managed.md).

*Research analytics, not investment advice. Past factor returns are not a forecast.*

## 1. Question and hypotheses

Moreira and Muir (2017) scale a factor's exposure by the inverse of its previous-month realised
variance. They report positive alphas of the managed factor against the original one.
Cederburg, O'Doherty, Wang and Yan (2020) argue that a real-time investor does not know the
scaling constant in advance, and that this gain then mostly disappears.

The hypotheses were fixed before running:

- **H1 (replication, in sample).** For each factor, the managed version has a positive alpha
  against the unmanaged factor.
- **H2 (implementability, out of sample).** In real time and after costs, the managed version
  does **not** have a significantly higher Sharpe ratio than the unmanaged factor, after
  correcting for the six factors tested.

## 2. Data and assumptions

**Factors** (US, USD, simple returns, from the Kenneth R. French Data Library):

- Mkt-RF, SMB and HML from the three-factor files;
- RMW and CMA from the five-factor (2x3) files;
- Mom from the momentum files.

**How each series is used:**

- Monthly returns come from the monthly files.
- Realised variances come from the daily files.
- Mkt-RF is an excess return; the others are zero-cost long-short returns.

**Vintage:** the files were downloaded on 2026-11-12 and stored unchanged in the git-ignored raw
store. They are not redistributed.

| File | Bytes | SHA-256 |
|---|---:|---|
| `F-F_Research_Data_Factors_daily_CSV.zip` | 178,326 | `96c23b88e651cbfff3740a53f8225e59ee39893371e96385a1d8125ec2cd9c89` |
| `F-F_Research_Data_Factors_CSV.zip` | 13,078 | `b03d39e4bb253dda0f14893db3b78e64b40b8d6549a0fc0fd4111dae84c98618` |
| `F-F_Research_Data_5_Factors_2x3_daily_CSV.zip` | 150,489 | `e58577223032aa45071a46686f7068900c371b516c9eb04e28e974c34264f84f` |
| `F-F_Research_Data_5_Factors_2x3_CSV.zip` | 11,971 | `17d7a575e71d6764a70ddec3f8d887756c0eebf3a60f64d6ba95d2adde3fed26` |
| `F-F_Momentum_Factor_daily_CSV.zip` | 85,338 | `e56d5bc845544e2993e77353b12c611cfce3149ef754f9b59fc67904ddadd369` |
| `F-F_Momentum_Factor_CSV.zip` | 5,603 | `27ed60e5b2caa9ea334a261cddfa864a9926f6bf45e9677c95dfd835c5abb315` |

**Samples.** No values are missing inside any window.

| Run | Window | Managed months, in sample | First out-of-sample month |
|---|---|---|---|
| Main | data up to 2026-09 | Mkt-RF, SMB, HML: 1926-08 to 2026-09 (1202). RMW, CMA: 1963-08 to 2026-09 (758). Mom: 1927-01 to 2026-09 (1197) | 1936-08 (Mkt-RF, SMB, HML), 1973-08 (RMW, CMA), 1937-01 (Mom) |
| Paper sample | data up to 2015-12 | the same start months, ending 2015-12 | the same |
| Sensitivity | same as the main run | the same months as the main run | the same |

The sensitivity run differs from the main run only in using demeaned daily returns for the
realised variance.

## 3. Specification

The specification was fixed in the design note:

- **Signal:** $1/RV_{t-1}$, where $RV_{t-1}$ is the sum of squared daily returns in the
  previous calendar month.
- **In sample:**
  - $f^\sigma_t = c\,f_t/RV_{t-1}$, with $c$ set on the **full sample** so that $f^\sigma$ and
    $f$ have the same volatility. This uses future information, as in the paper.
  - Spanning regression $f^\sigma_t=\alpha+\beta f_t+\varepsilon_t$ with Newey–West standard
    errors (6 lags).
- **Out of sample:**
  - $c_t$ is estimated from the months before $t$ only, on an expanding window after a
    120-month burn-in.
  - Weight $w_t=\min(c_t/RV_{t-1},\,\text{cap})$, with caps of 5× (main), 2× and none.
  - Costs of 0, 10 or 25 bp per unit of factor exposure traded, charged on $|w_t-w_{t-1}|$.
  - Comparison with the unmanaged factor on the same months: Ledoit–Wolf HAC test of the
    Sharpe-ratio difference (6 lags) and a stationary-bootstrap 95 % interval (mean block 6,
    2000 resamples, seed 20261112).
- **Multiple testing:**
  - Holm and Benjamini–Hochberg across the six factors, separately within each cap and cost
    pair.
  - Deflated Sharpe ratio of the best of all variants. Each run has 54 variants (6 factors × 3
    caps × 3 costs), and the trial ledger records 3 configurations, so N = 162.

**Reproduce:**

```bash
uv run qrlab run configs/studies/volatility_managed_full.toml
uv run qrlab run configs/studies/volatility_managed_paper.toml
uv run qrlab run configs/studies/volatility_managed_demeaned.toml
```

The configs point at this vintage of the raw files; another vintage needs new paths and may
give slightly different numbers. Outputs go to `results/` (git-ignored): tables, the HTML
report and `record.json` with the hashes of the inputs and of the code version.

## 4. In-sample results (full-sample $c$: look-ahead by construction)

Main run, 1926–2026:

| Factor | α p.a. | t (HAC) | p Holm | β | Appraisal p.a. | R² |
|---|---:|---:|---:|---:|---:|---:|
| Mkt-RF | 4.34 % | 2.73 | 0.026 | 0.62 | 0.30 | 0.39 |
| SMB | −0.80 % | −0.83 | 0.818 | 0.63 | −0.09 | 0.40 |
| HML | 1.63 % | 1.47 | 0.423 | 0.54 | 0.16 | 0.29 |
| RMW | 2.52 % | 2.96 | 0.016 | 0.56 | 0.38 | 0.32 |
| CMA | 0.28 % | 0.46 | 0.818 | 0.67 | 0.05 | 0.45 |
| Mom | 11.85 % | 6.49 | <0.001 | 0.46 | 0.82 | 0.21 |

**Paper sample (up to 2015):** the alphas are 4.68 % (Mkt-RF, t 2.80), −0.84 % (SMB), 1.71 %
(HML), 2.52 % (RMW, t 2.77), 0.20 % (CMA) and 12.67 % (Mom, t 6.39). The same three factors are
significant after Holm.

**Demeaned variance:** the alphas change by at most 0.3 percentage points. The same three
factors are significant.

The pattern matches the paper's main finding qualitatively:

- the largest alpha is momentum's;
- the market's is positive and significant;
- SMB's and CMA's are close to zero.

Exact figures differ from the published ones because the data have been revised since and the
standard errors are computed differently.

## 5. Out-of-sample results (real-time $c_t$, after costs)

Main run, cap 5×. Annualised Sharpe ratios; z and the Holm p-value test managed minus unmanaged:

| Factor | SR factor | SR managed, 0 bp | 10 bp | 25 bp | z (0 / 10 / 25 bp) | p Holm (0 / 10 / 25 bp) | Mean weight | Turnover p.a. |
|---|---:|---:|---:|---:|---|---|---:|---:|
| Mkt-RF | 0.52 | 0.44 | 0.40 | 0.35 | −0.87 / −1.26 / −1.85 | 1.00 / 0.62 / 0.19 | 1.49 | 8.9 |
| SMB | 0.18 | 0.08 | 0.03 | −0.05 | −1.14 / −1.77 / −2.68 | 1.00 / 0.39 / **0.037** | 1.35 | 7.1 |
| HML | 0.40 | 0.40 | 0.35 | 0.27 | 0.09 / −0.53 / −1.46 | 1.00 / 0.92 / 0.29 | 1.84 | 9.5 |
| RMW | 0.38 | 0.56 | 0.47 | 0.33 | 1.46 / 0.74 / −0.37 | 0.71 / 0.92 / 0.71 | 0.77 | 4.1 |
| CMA | 0.47 | 0.40 | 0.31 | 0.17 | −0.66 / −1.55 / −2.86 | 1.00 / 0.48 / **0.026** | 0.97 | 5.2 |
| Mom | 0.51 | 0.88 | 0.82 | 0.75 | 3.27 / 2.81 / 2.12 | **0.007** / **0.030** / 0.137 | 1.77 | 9.8 |

Turnover p.a. is $\sum|\Delta w|$ per year: 9.8 means the strategy trades about ten times its
exposure each year.

**Other caps for momentum** (the factor with the largest differences):

- With a 2× cap the managed Sharpe ratios are 0.87, 0.83 and 0.78 at 0, 10 and 25 bp, with Holm
  p-values 0.003, 0.009 and 0.040.
- Without a cap the weight reaches 24.8×, the Sharpe ratios fall to 0.71, 0.65 and 0.57, and no
  difference is significant (Holm p-values of 0.84 or more).

**Other factors across caps:** the managed Sharpe ratio is higher in 17 of the 54 variants of
the main run. For Mkt-RF, SMB, HML, RMW and CMA, no cap and cost combination gives a
significantly *higher* Sharpe ratio. The significant differences for these factors are all
*negative* and appear at 25 bp: SMB and CMA at cap 5×, and CMA without a cap.

**Paper sample:** the conclusions are the same:

- momentum is significantly better at cap 5× with 0 bp, and at cap 2× with 0 and 10 bp;
- SMB, HML and CMA are significantly worse at 25 bp;
- nothing else is significant.

**Demeaned variance:** momentum is significantly better at caps 5× and 2× with 0 and 10 bp.
CMA without a cap is significantly worse at 25 bp.

**Multiple testing beyond the pre-specified families.** The design corrected across the six
factors within each cap and cost pair. If Holm is applied across all 54 variants of a run
instead, only managed momentum survives:

- at cap 2×, 0 bp, in the main run (adjusted p 0.026);
- at cap 2×, 0 bp, in the demeaned run (adjusted p 0.048);
- no variant in the paper sample (smallest adjusted p 0.072).

**Deflated Sharpe ratio:** the best variant is momentum, cap 5×, 0 bp. Its DSR is 0.98 with
N = 162 trials, so its Sharpe ratio is unlikely to be positive only because of selection.
The DSR tests against **zero**, not against unmanaged momentum. The comparison with the
unmanaged factor is the HAC test above.

## 6. Conclusions

- **H1, partly supported.** In sample, the managed versions of Mkt-RF, RMW and Mom have
  positive alphas that remain significant after Holm, in all three runs. HML's alpha is positive
  but not significant, SMB's is negative and CMA's is close to zero.
- **H2, supported for five of the six factors.** In real time, Mkt-RF, SMB, HML, RMW and CMA
  never have a significantly higher net Sharpe ratio. At 25 bp, volatility management makes SMB
  and CMA significantly *worse*. This is consistent with Cederburg et al.: in-sample spanning
  alphas do not turn into real-time gains.
- **Momentum is the exception (H2 rejected).** With a leverage cap of 2× or 5×, real-time
  volatility-managed momentum has a higher net Sharpe ratio than momentum (0.82–0.88 against
  0.51 per year at 0–10 bp). The difference is significant within the pre-specified families in
  all three runs, and is in line with the known volatility-scaling result for momentum (Barroso
  and Santa-Clara 2015). The evidence is moderate, not decisive:
  - it depends on the cap: without one, the effect is not significant;
  - it weakens with costs;
  - corrected across all 54 variants, it survives only at cap 2× and 0 bp, and not in the
    paper sample;
  - it is subject to the cost limitation in §7.

## 7. Limitations

- **Costs:**
  - The cost model charges only the change in exposure $|w_t-w_{t-1}|$. It does not charge the
    managed strategy for trading more of the factor's own rebalancing when its average weight
    is above 1, for example 1.77 for momentum at cap 5×. Momentum is a high-turnover factor, so
    this favours the managed version. The 2× cap (mean weight 1.19) is less exposed to it.
  - "Per unit of exposure" means a 10 bp cost covers both legs of a long-short factor.
- **Funding:** leverage is financed implicitly at the one-month T-bill rate (Mkt-RF) or at no
  cost (long-short factors). No margin or shorting constraints are modelled.
- **The factors are not investable.** They are paper portfolios with no fees, market impact or
  short-sale costs.
- **Multiple testing:**
  - The families for correction (six factors within each cap and cost) were fixed in the
    design. Corrections across larger families are reported above and are stricter.
  - The DSR uses the dispersion of the Sharpe ratios within one run, as listed in the design
    note's deviations.
- **Data revisions:** the Ken French library revises history. Numbers depend on this vintage,
  whose hashes are listed above.
- **Fixed settings:** the HAC lags (6), the bootstrap block length (6) and the 120-month burn-in
  were fixed in advance and not tuned. Their sensitivity was not explored, to avoid a
  specification search.

## References

- Moreira, A. and Muir, T. (2017). Volatility-Managed Portfolios. *Journal of Finance* 72(4).
- Cederburg, S., O'Doherty, M. S., Wang, F. and Yan, X. (2020). On the performance of
  volatility-managed portfolios. *Journal of Financial Economics* 138(1).
- Barroso, P. and Santa-Clara, P. (2015). Momentum has its moments. *Journal of Financial
  Economics* 116(1).
- Ledoit, O. and Wolf, M. (2008). Robust performance hypothesis testing with the Sharpe ratio.
  *Journal of Empirical Finance* 15(5).
- Bailey, D. H. and López de Prado, M. (2014). The deflated Sharpe ratio. *Journal of Portfolio
  Management* 40(5).
