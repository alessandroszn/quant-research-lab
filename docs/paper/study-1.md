# Study 1: volatility-managed factors

## Question and hypotheses

Moreira and Muir (2017) scale a factor's exposure by the inverse of its realised variance in the
previous month. Against the unmanaged factor, the managed factor earns a positive alpha. The
scaling constant behind that result is set with the full sample, so it uses information a
real-time investor does not have. Cederburg, O'Doherty, Wang and Yan (2020) estimate the
constant in real time instead, and find that most of the gain disappears.

This study tests both findings on a recent vintage of the data, for six factors, with leverage
limits and transaction costs stated explicitly. The hypotheses were fixed in the design note
before any result was seen:

- **H1 (replication, in sample).** For each factor, the managed version has a positive alpha
  against the unmanaged factor.
- **H2 (implementability, real time).** In real time and after costs, the managed version does
  **not** have a significantly higher Sharpe ratio than the unmanaged factor, after correcting
  for the six factors tested.

H2 is the null of the real-time question. A significant net gain for a factor rejects it for
that factor.

## Data and specification

**Data.** The six factors are US, in USD, with simple returns, from the Kenneth R. French Data
Library: Mkt-RF, SMB and HML from the three-factor files, RMW and CMA from the five-factor
(2×3) files, and Mom from the momentum files. Monthly returns come from the monthly files.
Realised variances come from the daily files. Mkt-RF is an excess return; the other five are
zero-cost long-short returns. The files are stored unchanged with their hashes (Appendix A)
and are not redistributed.

In the main run, the managed series cover {{ s1_mkt_start }} to {{ s1_end }} for Mkt-RF, SMB
and HML ({{ s1_mkt_n }} months). They start in {{ s1_rmw_start }} for RMW and CMA
({{ s1_rmw_n }} months) and in {{ s1_mom_start }} for Mom ({{ s1_mom_n }} months). No value is
missing inside any window.

**Signal.** $RV_{t-1}$ is the sum of squared daily returns of the factor in the previous
calendar month. The exposure in month $t$ is proportional to $1/RV_{t-1}$, so the signal is
known before the month starts.

**In sample (H1).** The managed factor is $f^\sigma_t = c\,f_t/RV_{t-1}$. The constant $c$ is
set on the full sample so that $f^\sigma$ and $f$ have the same volatility. This uses future
information by construction, as in the original paper. The spanning regression is
$f^\sigma_t=\alpha+\beta f_t+\varepsilon_t$, with Newey–West standard errors (6 lags). We
report the annualised alpha, its HAC $t$-statistic, the appraisal ratio and $R^2$.

**Real time (H2).** The constant $c_t$ is estimated from the months before $t$ only, on an
expanding window after a 120-month burn-in. The weight is $w_t=\min(c_t/RV_{t-1},\,\text{cap})$,
with caps of 5× (main), 2× and none. Costs are 0, 10 or 25 bp per unit of factor exposure
traded, charged on $|w_t-w_{t-1}|$. The first real-time month is not charged. The unmanaged
factor carries no cost in this comparison: its own rebalancing costs are the same in both and
cancel. The real-time samples start in {{ s1_mkt_oos_start }} for Mkt-RF, SMB and HML
({{ s1_mkt_oos_n }} months), in {{ s1_rmw_oos_start }} for RMW and CMA ({{ s1_rmw_oos_n }}
months) and in {{ s1_mom_oos_start }} for Mom ({{ s1_mom_oos_n }} months).

The managed and unmanaged factors are compared on the same months. The tests are the
Ledoit–Wolf HAC test of the Sharpe-ratio difference (6 lags) and a stationary-bootstrap 95 %
interval (mean block length 6, 2,000 resamples).

**Multiple testing.** Holm and Benjamini–Hochberg corrections run across the six factors,
separately within each cap and cost pair. These families were fixed in the design. Each run
has 54 variants (6 factors × 3 caps × 3 costs). The trial ledger records {{ s1_tried }}
configurations, so the deflated Sharpe ratio (DSR) of the best variant uses
N = {{ s1_dsr_trials }} trials.

**Robustness runs.** Two variants were also fixed in advance. The *paper sample* ends in
{{ s1_paper_end }}, close to the original study. The *demeaned* run demeans daily returns within
the month before squaring them, as Moreira and Muir do; the main run sums raw squares.

## In-sample results

Main run, full-sample $c$ (look-ahead by construction):

```{include} _generated/s1_in_sample.md
```

After the Holm correction, {{ s1_is_rejections }} of the six alphas are significant:

- Mkt-RF: {{ s1_mkt_alpha }} a year, $t$ = {{ s1_mkt_alpha_t }}, Holm $p$ =
  {{ s1_mkt_alpha_holm }};
- RMW: {{ s1_rmw_alpha }}, $t$ = {{ s1_rmw_alpha_t }}, Holm $p$ = {{ s1_rmw_alpha_holm }};
- Mom: {{ s1_mom_alpha }}, $t$ = {{ s1_mom_alpha_t }}, with an appraisal ratio of
  {{ s1_mom_appraisal }}; its Holm $p$-value rounds to zero.

HML's alpha is positive, {{ s1_hml_alpha }}, but not significant (Holm $p$ =
{{ s1_hml_alpha_holm }}). SMB's is negative, {{ s1_smb_alpha }}, and CMA's is close to zero,
{{ s1_cma_alpha }}.

The pattern matches the original finding qualitatively. Momentum has the largest alpha. The
market's alpha is positive and significant. SMB's and CMA's are close to zero. The exact
figures differ from the published ones, because the library has revised its history since and
the standard errors are computed differently.

**H1 is partly supported.** It holds for Mkt-RF, RMW and Mom, not for HML, SMB and CMA. These
alphas describe a spanning property with a constant chosen in hindsight. They are not returns
an investor could have earned.

## Real-time results

Main run, cap 5×, annualised Sharpe ratios (SR) net of costs. The $z$-statistic and the Holm
$p$-value test managed minus unmanaged; turnover per year is $\sum|\Delta w|$:

```{include} _generated/s1_real_time.md
```

**Five factors show no real-time gain.** For Mkt-RF, SMB, HML, RMW and CMA, no cap and cost
combination gives a significantly higher net Sharpe ratio. The market's in-sample alpha is
significant, yet in real time the managed market has a Sharpe ratio of
{{ s1_mkt5_sr0 }} against {{ s1_mkt_sr }} before any cost. RMW comes closest to a gain: at
0 bp its managed Sharpe ratio is {{ s1_rmw5_sr0 }} against {{ s1_rmw_sr }}, with
$z$ = {{ s1_rmw5_z0 }} and Holm $p$ = {{ s1_rmw5_holm0 }}. At 25 bp it falls to
{{ s1_rmw5_sr25 }}.

For these five factors, the significant differences are all negative, and all at 25 bp:

- SMB at cap 5×: {{ s1_smb5_sr25 }} against {{ s1_smb_sr }}, Holm $p$ = {{ s1_smb5_holm25 }};
- CMA at cap 5×: {{ s1_cma5_sr25 }} against {{ s1_cma_sr }}, Holm $p$ = {{ s1_cma5_holm25 }};
- CMA without a cap: Holm $p$ = {{ s1_cmainf_holm25 }}.

Volatility management makes these two factors worse once trading is costly.

**Momentum is the exception.** The unmanaged factor has a Sharpe ratio of {{ s1_mom_sr }}.
At cap 5× the managed version reaches {{ s1_mom5_sr0 }}, {{ s1_mom5_sr10 }} and
{{ s1_mom5_sr25 }} at 0, 10 and 25 bp. The Holm $p$-values are {{ s1_mom5_holm0 }},
{{ s1_mom5_holm10 }} and {{ s1_mom5_holm25 }}. The result depends on the cap:

- at cap 2×, the Sharpe ratios are {{ s1_mom2_sr0 }}, {{ s1_mom2_sr10 }} and
  {{ s1_mom2_sr25 }}, with Holm $p$-values {{ s1_mom2_holm0 }}, {{ s1_mom2_holm10 }} and
  {{ s1_mom2_holm25 }};
- without a cap, the weight reaches {{ s1_mominf_maxw }}×. The Sharpe ratios fall to
  {{ s1_mominf_sr0 }}, {{ s1_mominf_sr10 }} and {{ s1_mominf_sr25 }}, and no difference is
  significant (Holm $p$-values of {{ s1_mominf_holm0 }} or more).

**H2 is supported for five of the six factors and rejected for momentum.** This matches
Cederburg et al. for the first five: in-sample spanning alphas do not become real-time gains.
The momentum result is in line with the known volatility-scaling result for momentum (Barroso
and Santa-Clara 2015).

## Statistical and economic significance

**Statistical significance.** Within the pre-specified families, Holm rejects
{{ s1_oos_rejections }} of the 54 real-time comparisons in the main run. They are the momentum
gains at caps 5× and 2× and the negative differences for SMB and CMA at 25 bp, all listed
above.

The bootstrap intervals agree with the HAC tests. For momentum at cap 5× and 0 bp, the 95 %
interval of the monthly Sharpe-ratio difference is {{ s1_mom5_boot_low }} to
{{ s1_mom5_boot_high }}, which excludes zero. For RMW at the same settings it is
{{ s1_rmw5_boot_low }} to {{ s1_rmw5_boot_high }}, which includes zero.

The families for correction were fixed in the design. The full report also applies Holm across
all 54 variants of a run, a stricter family chosen after the fact. Under that correction only
managed momentum at cap 2× and 0 bp survives, in the main and demeaned runs. No variant
survives in the paper sample.

The best of all variants is momentum at cap 5× and 0 bp. Its DSR is {{ s1_dsr }} with
N = {{ s1_dsr_trials }} trials, so its Sharpe ratio is unlikely to be positive only because it
was selected. The DSR tests against **zero**, not against unmanaged momentum. The comparison
with the unmanaged factor is the HAC test above.

**Economic significance.** The in-sample alphas are large: {{ s1_mom_alpha }} a year for
momentum and {{ s1_mkt_alpha }} for the market. For five factors, none of this reaches a
real-time investor. For momentum, the real-time Sharpe ratio rises before costs from
{{ s1_mom_sr }} to {{ s1_mom5_sr0 }} at cap 5×. The gain is bought with leverage and trading.
At cap 5× the mean weight is {{ s1_mom5_weight }} and the strategy trades
{{ s1_mom5_turnover }} times its exposure a year. At cap 2× these are {{ s1_mom2_weight }} and
{{ s1_mom2_turnover }}. At 25 bp the managed Sharpe ratio is {{ s1_mom2_sr25 }} at cap 2×,
against {{ s1_mom5_sr25 }} at cap 5×.

Three features of the setup favour the managed strategies or leave costs out:

- **Costs.** The model charges only the change in exposure. It does not charge the managed
  strategy for trading more of the factor's own rebalancing when its mean weight is above one.
  Momentum is a high-turnover factor, so this favours managed momentum, more at cap 5× than at
  cap 2×. A cost "per unit of exposure" covers both legs of a long-short factor.
- **Funding.** Leverage is financed implicitly at the one-month T-bill rate (Mkt-RF) or at no
  cost (long-short factors). No margin or shorting constraints are modelled.
- **Investability.** The factors are paper portfolios, with no fees, market impact or
  short-sale costs.

The evidence for momentum is therefore moderate, not decisive. It depends on the cap. It
weakens with costs. It survives the stricter correction only at cap 2× and 0 bp, and not in the
paper sample. It is subject to the cost limitation above.

## Robustness

**Paper sample** (data to {{ s1_paper_end }}; {{ s1_paper_mkt_n }} months for Mkt-RF). In sample,
the alphas are {{ s1_paper_mkt_alpha }} for Mkt-RF ($t$ = {{ s1_paper_mkt_alpha_t }}),
{{ s1_paper_rmw_alpha }} for RMW ($t$ = {{ s1_paper_rmw_alpha_t }}) and
{{ s1_paper_mom_alpha }} for Mom ($t$ = {{ s1_paper_mom_alpha_t }}). The same
{{ s1_paper_is_rejections }} factors are significant after Holm. In real time the conclusions
are the same:

- momentum is significantly better at cap 5× with 0 bp ({{ s1_paper_mom5_sr0 }} against
  {{ s1_paper_mom_sr }}, Holm $p$ = {{ s1_paper_mom5_holm0 }}), and at cap 2× with 0 and 10 bp
  (Holm $p$ = {{ s1_paper_mom2_holm0 }} and {{ s1_paper_mom2_holm10 }});
- SMB, HML and CMA are significantly worse at 25 bp;
- nothing else is significant.

Holm rejects {{ s1_paper_oos_rejections }} comparisons in this run, and the DSR of the best
variant is {{ s1_paper_dsr }}.

**Demeaned variance.** The in-sample alphas change only slightly: {{ s1_dm_mkt_alpha }} for
Mkt-RF, {{ s1_dm_rmw_alpha }} for RMW and {{ s1_dm_mom_alpha }} for Mom. The same
{{ s1_dm_is_rejections }} factors are significant. In real time, momentum is significantly
better at caps 5× and 2× with 0 and 10 bp (Holm $p$ at 0 bp: {{ s1_dm_mom5_holm0 }} and
{{ s1_dm_mom2_holm0 }}). CMA without a cap is significantly worse at 25 bp (Holm $p$ =
{{ s1_dm_cmainf_holm25 }}). Holm rejects {{ s1_dm_oos_rejections }} comparisons, and the DSR of
the best variant is {{ s1_dm_dsr }}.

**Fixed settings and data.** The HAC lags, the bootstrap block length and the burn-in were
fixed in advance and not tuned. Their sensitivity was not explored, to avoid a specification
search. The French library revises its history, so the numbers depend on this vintage.

The data hashes, the complete tables for every cap and the reproduction commands are in the
[full report](../studies/01-volatility-managed.md).
