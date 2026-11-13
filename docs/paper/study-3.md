# Study 3: the factor zoo

*Research analytics, not investment advice. All returns in this section are gross long-short
returns of paper portfolios, before trading costs.*

## Question and hypotheses

Hundreds of published firm characteristics are claimed to predict the cross-section of stock
returns. This study asks how much of that literature survives two kinds of scrutiny.

The first is multiple testing. Harvey, Liu and Zhu (2016) argue that, with so many tests, the
usual threshold of t > 2 is too low. They propose a bar of about t > 3 and formal
corrections for multiple comparisons. The second is out-of-sample decay. McLean and Pontiff
(2016) find that long-short returns fall after the original sample ends and fall further
after publication, but do not disappear.

Open Source Asset Pricing (Chen and Zimmermann 2022) replicates a large set of published
predictors with public code. It allows both questions to be asked on one consistent dataset.

Three hypotheses were fixed in the design note before any result was seen:

- **H1 (descriptive).** How many predictors are significant in their original sample under
  each of five rules: a single test at 5 %, t > 3, and the Holm, Benjamini–Hochberg (BH) and
  Benjamini–Yekutieli (BY) corrections at 5 %. No direction is claimed; the counts are the
  result.
- **H2.** Long-short returns are lower after the original sample, and lower again after
  publication. The test is a panel regression with predictor fixed effects and standard
  errors clustered by month.
- **H3.** The equal-weighted composite of all predictors still earns a positive return after
  publication.

An honest null result would have been reported as such.

## Data and specification

**Data.** The source is Open Source Asset Pricing, release 2026.10, licensed CC BY 4.0. Two
files are used: the monthly long-short returns of each predictor and the signal
documentation. The documentation gives each predictor's publication year, original sample
years and the strength of the original result. The firm-level files, which derive from
commercial databases, are not used. Each long-short return is signed as in the original
paper, so a positive mean is the effect the authors reported. The study's sample ends in
{{ s3_end }}. The raw files are stored unchanged and are not redistributed; Appendix A lists
their hashes.

**Universes.** Both were fixed in the design note:

- **Main:** predictors whose original result is classified as "clear".
- **Robustness:** "clear" and "likely" predictors together.

**Exclusions.** The design said the run would stop if any predictor had more than 1 % of its
months missing inside its series. Some did. Before any result was seen, the decision was to
exclude them instead and to list them. This removed {{ s3_excl_clear }} "clear" predictors
and {{ s3_excl_broad }} predictors from the broad set. The main universe therefore holds
{{ s3_n_clear }} predictors and the broad universe {{ s3_n_broad }}. Smaller gaps are left
out of each predictor's statistics, never filled.

**Phases.** Each predictor's months are split into three phases:

- **in-sample:** the years of the original paper's sample;
- **post-sample:** from the January after the sample ends to the December of the publication
  year;
- **post-publication:** from the following January on.

Months before the original sample are excluded. Only the publication year is known, so months
in that year count as post-sample. This is a conservative deviation from McLean and Pontiff,
who use the publication date. For the "clear" predictors, in-sample months run from
{{ s3_is_start }} to {{ s3_is_end }}, and post-publication months from {{ s3_pp_start }} to
{{ s3_pp_end }}.

**Per-predictor tests.** In each phase, the mean long-short return is tested against zero
with a Newey–West t-statistic (6 lags) and a two-sided p-value. A phase is tested only if it
has at least 12 months. The Holm, BH and BY corrections are applied at 5 % across the
predictors of each universe. BY remains valid under any dependence between the predictors.

**Decay regression.** The pooled panel regression is

$$
r_{it}=\alpha_i+\beta_{ps}\,\text{PostSample}_{it}+\beta_{pp}\,\text{PostPub}_{it}+\varepsilon_{it},
$$

with predictor fixed effects $\alpha_i$ and standard errors clustered by month, which absorbs
the cross-sectional correlation between predictors. The decay is each coefficient divided by
the pooled in-sample mean, as in McLean and Pontiff. The difference
$\beta_{pp}-\beta_{ps}$ is tested with the clustered covariance. All tests are two-sided.

**Composites.** Each month, the returns of the predictors in a given phase are averaged with
equal weights. The mean of each composite is tested with a Newey–West t-statistic (6 lags).

**Trial ledger.** The study ran {{ s3_tried }} configurations: the main universe and the
robustness universe. Both were fixed before the run.

## In-sample results

Table 3.1 gives the H1 counts for the {{ s3_is_tested }} "clear" predictors, each tested in
its original sample.

**Table 3.1.** Predictors significant in their original sample, "clear" universe.

```{include} _generated/s3_in_sample.md
```

Most published predictors pass a single test in their own sample: {{ s3_is_single_share }}
of them. The BH correction leaves this share unchanged at {{ s3_is_bh_share }}. Raising the
bar matters. Under the t > 3 threshold of Harvey, Liu and Zhu, {{ s3_is_t3_share }} survive.
Under BY, which is valid for any dependence, {{ s3_is_by_share }} survive. Under Holm, the
strictest rule, {{ s3_is_holm_share }} survive.

Every significant predictor has a positive t-statistic, and no "clear" predictor has a
negative in-sample t-statistic. This is expected: the signs come from the original papers.

The reading of H1 is twofold. The factor zoo is not mostly made of false positives within its
own samples. But a sizeable minority of published predictors, of a size that depends on the
rule, would not have cleared a multiple-testing bar.

These in-sample tests are biased upward by construction. Each predictor was published because
it worked in that sample, with that sign. The in-sample counts describe the literature; they
are not evidence that the predictors work.

## Out-of-sample and post-publication results

**Per-predictor tests after publication.** Table 3.2 applies the same five rules to each
predictor's post-publication months. Of the {{ s3_pp_tested }} "clear" predictors with enough
post-publication months, {{ s3_pp_single_n }} pass a single test and {{ s3_pp_by_n }} pass BY.

**Table 3.2.** Predictors significant after publication, "clear" universe.

```{include} _generated/s3_post_publication.md
```

These counts are context, not part of H1. The post-publication periods are shorter than the
original samples, so the counts mix lower returns with lower statistical power. The decay
regression separates the two.

**Decay (H2).** Table 3.3 gives the panel regression for both universes. Coefficients and
standard errors are in percent per month.

**Table 3.3.** Decay regression with predictor fixed effects and month-clustered standard
errors.

| | Clear | Clear + likely |
|---|---:|---:|
| Pooled in-sample mean (per month) | {{ s3_in_mean }} | {{ s3_b_in_mean }} |
| $\beta_{ps}$ (s.e.) | {{ s3_beta_ps }} ({{ s3_se_ps }}) | {{ s3_b_beta_ps }} ({{ s3_b_se_ps }}) |
| p-value, $\beta_{ps}$ | {{ s3_p_ps }} | {{ s3_b_p_ps }} |
| Decay after the sample | {{ s3_decay_ps }} | {{ s3_b_decay_ps }} |
| $\beta_{pp}$ (s.e.) | {{ s3_beta_pp }} ({{ s3_se_pp }}) | {{ s3_b_beta_pp }} ({{ s3_b_se_pp }}) |
| p-value, $\beta_{pp}$ | {{ s3_p_pp }} | {{ s3_b_p_pp }} |
| Decay after publication | {{ s3_decay_pp }} | {{ s3_b_decay_pp }} |
| $\beta_{pp}-\beta_{ps}$ | {{ s3_diff }} | {{ s3_b_diff }} |
| p-value, difference | {{ s3_p_diff }} | {{ s3_b_p_diff }} |
| Observations | {{ s3_nobs }} | {{ s3_b_nobs }} |
| Predictors | {{ s3_n_clear }} | {{ s3_n_broad }} |
| Months | {{ s3_months }} | {{ s3_b_months }} |

This is the headline result of the study. For the "clear" predictors, long-short returns
are {{ s3_decay_ps_round }} lower after the original sample and {{ s3_decay_pp_round }} lower
after publication, relative to the pooled in-sample mean. Both coefficients are highly
significant. H2 is supported. The pattern is close to McLean and Pontiff's estimates, on a
larger set of predictors and with additional years of data.

**Composites (H3).** Table 3.4 gives the equal-weighted composite of the "clear" predictors
in each phase.

**Table 3.4.** Equal-weighted composites by phase, "clear" universe.

| Phase | Months | Predictors per month | Mean per month | t (Newey–West) |
|---|---:|---:|---:|---:|
| In-sample | {{ s3_comp_is_months }} | {{ s3_comp_is_preds }} | {{ s3_comp_is_mean }} | {{ s3_comp_is_t }} |
| Post-sample | {{ s3_comp_ps_months }} | {{ s3_comp_ps_preds }} | {{ s3_comp_ps_mean }} | {{ s3_comp_ps_t }} |
| Post-publication | {{ s3_comp_pp_months }} | {{ s3_comp_pp_preds }} | {{ s3_comp_pp_mean }} | {{ s3_comp_pp_t }} |

After publication, the composite earns {{ s3_comp_pp_mean }} per month with a t-statistic of
{{ s3_comp_pp_t }}. H3 is supported: the average published predictor still earns a positive
gross long-short return after publication.

The composites average different predictors in each phase, over different years and with
different numbers of predictors per month. Their levels are therefore not comparable across
phases, and they are not the decay result. The within-predictor comparison is the panel
regression of Table 3.3.

## Statistical and economic significance

**Statistical significance.** Both decay coefficients have small p-values in both universes
(Table 3.3). Month clustering accounts for the correlation between predictors in the same
month. The further decline at publication, beyond the post-sample decline, is a weaker
result. It is significant at 5 % for the "clear" predictors (p = {{ s3_p_diff }}) and
borderline for the broad set (p = {{ s3_b_p_diff }}). The H1 counts are descriptive and carry
no single test. The post-publication composite's t-statistic of {{ s3_comp_pp_t }} is well
above the t > 3 bar.

**Economic significance.** The pooled in-sample mean of the "clear" predictors is
{{ s3_in_mean }} per month. After publication the average anomaly is much smaller, but it does
not vanish. This holds only before costs. These are gross returns of paper long-short portfolios. Many
anomalies are costly to trade. Whether the post-publication premium survives costs is a separate question
(Chen and Velikov 2023), not answered here.

Two further cautions limit the economic reading. Predictors overlap heavily and are
correlated, so the counts in Tables 3.1 and 3.2 are not counts of independent effects. And
the in-sample results inherit the selection of the original papers, so only the post-sample
and post-publication results speak to whether a predictor works out of sample.

## Robustness

**Broader universe.** Adding the "likely" predictors lowers every in-sample share. Under a
single test, {{ s3_b_is_single_share }} of the {{ s3_b_is_tested }} predictors are
significant; under BH, {{ s3_b_is_bh_share }}; under BY, {{ s3_b_is_by_share }}; under t > 3,
{{ s3_b_is_t3_share }}; under Holm, {{ s3_b_is_holm_share }}. The ordering of the rules is the
same as for the "clear" set. The decay estimates barely change: {{ s3_b_decay_ps }} after the
sample and {{ s3_b_decay_pp }} after publication (Table 3.3). The post-publication composite
of the broad set earns {{ s3_b_comp_pp_mean }} per month (t = {{ s3_b_comp_pp_t }}).

**Exclusions.** The predictors excluded for gaps were chosen by a data-quality rule fixed
before any result was seen. Results depend on this release of the data, whose files are
identified by their hashes in Appendix A.

**What is not controlled.**

- *Calendar time.* Post-publication months fall mostly in the later part of the sample. Part
  of the decay may be a general decline of anomaly returns over time, not publication itself.
  The regression has no time fixed effects or trends. McLean and Pontiff address this with
  time trends; it is a possible extension.
- *Publication timing.* The publication year is a coarse proxy. Working papers circulate
  earlier, which biases the test against finding a decay at publication.
- *Costs.* No trading costs are modelled.

The [full report](../studies/03-factor-zoo.md) gives the data checks, the list of excluded
predictors and the reproduction commands.
