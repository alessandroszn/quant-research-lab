# Study 3 — The factor zoo: multiple testing and post-publication decay

Run on 2026-11-12 with Open Source Asset Pricing release 2026.10. The design note was approved
before any result was seen: [`docs/design/5.3-study-3-factor-zoo.md`](../design/5.3-study-3-factor-zoo.md).

*Research analytics, not investment advice. Gross long-short returns of paper portfolios.*

*Re-run on 2026-11-13 from a clean checkout of commit f8ee46c, with the same data: every
output was byte-identical.*

Data: Chen, A. Y. and Zimmermann, T. (2022), *Open Source Cross-Sectional Asset Pricing*,
Critical Finance Review 11(2); Open Source Asset Pricing, licensed CC BY 4.0.

## 1. Questions and hypotheses

Hundreds of published characteristics are claimed to predict stock returns. Two papers ask how
much of this survives:

- **Harvey, Liu and Zhu (2016):** with so many tests, a t-statistic of 2 is too low a bar.
- **McLean and Pontiff (2016):** long-short returns fall after the original sample ends, and
  fall further after publication.

The hypotheses were fixed before running:

- **H1 (descriptive).** How many predictors are significant in their original sample under
  each rule:
  - single test at 5 %;
  - t > 3;
  - Holm, Benjamini–Hochberg (BH) and Benjamini–Yekutieli (BY) at 5 %.
- **H2.** Returns are lower after the original sample, and lower again after publication: a
  panel regression with predictor fixed effects and errors clustered by month.
- **H3.** The post-publication equal-weighted composite is still positive.

## 2. Data and assumptions

**Source:** Open Source Asset Pricing, Hugging Face `OpenSourceAP/CrossSection`, revision
`ad1dfba5a6d80c4ce53ce6b8127f5a949dda1e40` (release 2026.10). The files were downloaded on
2026-11-12, stored unchanged in the git-ignored raw store, and are not redistributed.

| File | Bytes | SHA-256 |
|---|---:|---|
| `Portfolios/Full Sets OP/PredictorLSretWide.parquet` | 1,439,671 | `fc01df25d4383153cb3ae9e0dd730cc34b6d15a5207abeff09f34beda45bca58` |
| `SignalDoc.csv` | 183,100 | `0ceb11020c2138c2477b732948beaac2e67ccaad8428753e3a79af2bb5ea0178` |

**Contents:**

- Monthly long-short returns of 212 predictors, January 1926 to December 2025.
- The returns are signed as in the original papers (the original papers' construction).
- The original publications span 1973–2016 (median 2006). Their original samples end between
  1968 and 2014.

**Universes, fixed in the design:**

- **Main:** the 165 predictors whose original result is "clear".
- **Robustness:** the 212 "clear" and "likely" predictors together.

**Phases of each predictor's months:**

- **In-sample:** the original sample years.
- **Post-sample:** from the January after the sample ends to the December of the publication
  year.
- **Post-publication:** from the following January on.
- Months before the original sample are excluded.

**Exclusions** (approved deviation):

- 6 predictors have more than 1 % of their months missing inside their series:
  - "clear": DivOmit 3.4 %, ChNAnalyst 3.4 %, MS 2.8 %, ExclExp 2.0 %, BetaLiquidityPS 1.5 %;
  - "likely": AdExp 12.5 %.
- The design said the run would stop in that case. You chose, before any result was seen, to
  exclude these predictors instead.
- That leaves 160 "clear" and 206 "clear and likely" predictors.
- Up to 10 other predictors have small gaps, under 1 % (8 in the "clear" universe). Those
  months are left out, never filled.

**Data checks:**

- Every predictor in the documentation has a return series.
- The documentation's extra categories, "Drop" (5 signals) and "indirect" predictability (100
  placebos), were not expected by the parser. The strict parser refused them; they are now
  accepted and are not used.

## 3. Specification

- **Per-predictor tests:**
  - mean long-short return of each phase, Newey–West t-statistic (6 lags), two-sided p-value;
  - a phase is tested only with at least 12 months.
- **Corrections:** Holm, BH and BY at 5 % across the predictors of the universe. BY is valid
  under any dependence between predictors.
- **Decay regression:**
  - $r_{it}=\alpha_i+\beta_{ps}\text{PostSample}_{it}+\beta_{pp}\text{PostPub}_{it}+\varepsilon_{it}$;
  - predictor fixed effects;
  - errors clustered by month, which covers cross-sectional correlation.
- **Decay:** the coefficient divided by the pooled in-sample mean.
- **Composites:** each month, the equal-weighted average of the predictors in a phase, with a
  Newey–West test of its mean.
- **Trial ledger:** 2 configurations.

**Reproduce:**

```bash
uv sync --extra parquet
uv run qrlab run configs/studies/factor_zoo_clear.toml
uv run qrlab run configs/studies/factor_zoo_broad.toml
```

## 4. Results

### H1 — How many predictors are significant in their original samples

| Rule | Clear (160 tested) | Clear + likely (206 tested) |
|---|---:|---:|
| Single test, p ≤ 0.05 | 148 (92.5 %) | 169 (82.0 %) |
| t > 3 (Harvey–Liu–Zhu) | 101 (63.1 %) | 111 (53.9 %) |
| Holm | 83 (51.9 %) | 88 (42.7 %) |
| Benjamini–Hochberg | 148 (92.5 %) | 166 (80.6 %) |
| Benjamini–Yekutieli | 113 (70.6 %) | 117 (56.8 %) |

**Observations:**

- All significant predictors have positive t-statistics, as expected: the signs come from the
  original papers.
- None of the "clear" predictors has a negative in-sample t-statistic.

**After publication**, the same tests on each predictor's later months give, for "clear":

- single test: 42 of 159 significant;
- t > 3: 17;
- Holm: 8; BH: 23; BY: 9.

These later periods are shorter: the median publication year is 2006. So these counts mix
lower returns with lower power; the decay regression below separates the two.

### H2 — Decay after the sample and after publication

| | Clear | Clear + likely |
|---|---:|---:|
| Pooled in-sample mean | 0.740 % / month | 0.672 % / month |
| $\beta_{post\text{-}sample}$ (s.e.) | −0.257 % (0.074 %) | −0.237 % (0.065 %) |
| p-value | 0.0006 | 0.0002 |
| Decay post-sample | **−34.7 %** | **−35.3 %** |
| $\beta_{post\text{-}publication}$ (s.e.) | −0.432 % (0.063 %) | −0.376 % (0.056 %) |
| p-value | < 0.0001 | < 0.0001 |
| Decay post-publication | **−58.4 %** | **−55.9 %** |
| Post-publication minus post-sample | −0.175 % (p = 0.039) | −0.139 % (p = 0.056) |
| Observations / predictors / months | 106,497 / 160 / 1,194 | 135,079 / 206 / 1,200 |

### H3 — Composites by phase

| Phase | Months | Predictors per month | Mean per month (clear) | t (HAC) |
|---|---:|---:|---:|---:|
| In-sample | 1,062 | 55.7 | 0.842 % | 10.18 |
| Post-sample | 540 | 16.0 | 0.509 % | 6.13 |
| Post-publication | 624 | 62.1 | 0.676 % | 5.97 |

- **Clear + likely, post-publication:** 0.531 % per month, t = 5.48.
- **Predictors with a positive post-publication mean:** 87 % (clear) and 83 % (broad).
- **Median monthly mean, clear predictors:** 0.65 % in sample against 0.26 % after publication.

The composites mix different predictors in each phase (different years, different numbers of
predictors), so their levels are **not** comparable across phases. The within-predictor
comparison is the decay regression.

## 5. Conclusions

- **H1:**
  - Most published predictors pass a single test in their original sample: 92.5 % of the
    "clear" ones.
  - Raising the bar matters. Under Harvey–Liu–Zhu's t > 3, 63 % survive; under Holm, 52 %;
    under BY, valid for any dependence, 71 %. For "clear and likely" these are 54 %, 43 % and
    57 %.
  - The factor zoo is not mostly false positives in its own samples. But a sizeable minority,
    roughly a third to a half depending on the rule, would not have cleared a multiple-testing
    bar.
- **H2 is supported:**
  - Returns are 35 % lower after the original sample and 58 % lower after publication, both
    highly significant.
  - This is very close to McLean and Pontiff's estimates of about 26 % and 58 %, on a
    larger set of predictors (160 here against their 97) and with more than a decade of
    additional data.
  - The extra decline at publication is significant for "clear" predictors (p = 0.039) and
    borderline for the broad set (p = 0.056).
- **H3 is supported:**
  - After publication, the average predictor still earns a positive gross long-short return:
    the composite earns 0.68 % per month (t = 6.0), and 87 % of predictors are positive.
  - Publication roughly halves the anomalies, but does not remove them, *before costs*.

## 6. Limitations

- **In-sample tests are biased upward by construction.** Each predictor was published because
  it worked in that sample, with that sign.
- **The publication year is a proxy.** Post-publication starts the January after it. Working
  papers circulate earlier, which biases against finding a decay at publication.
- **Calendar time is not controlled.** The post-publication months fall mostly in 2000–2025.
  Part of the decay may be a general decline of anomaly returns over time, not publication
  itself; there are no time fixed effects here. McLean and Pontiff address this with time
  trends; this is recorded as a possible extension.
- **No trading costs.** These are gross paper-portfolio returns, and many anomalies are costly
  to trade. Net survival is a separate question (Chen and Velikov 2023), recorded in
  `docs/IDEAS.md`.
- **Overlap.** Predictors are correlated and overlap heavily. Month clustering and BY account
  for this statistically, but the counts are not counts of independent effects.
- **Exclusions.** 6 predictors with gaps were excluded and 10 have small gaps; results depend
  on this OSAP release (hashes above).

## References

- Chen, A. Y. and Zimmermann, T. (2022). Open source cross-sectional asset pricing. *Critical
  Finance Review* 11(2).
- Harvey, C. R., Liu, Y. and Zhu, H. (2016). … and the cross-section of expected returns.
  *Review of Financial Studies* 29(1).
- McLean, R. D. and Pontiff, J. (2016). Does academic research destroy stock return
  predictability? *Journal of Finance* 71(1).
- Benjamini, Y. and Yekutieli, D. (2001). The control of the false discovery rate in multiple
  testing under dependency. *Annals of Statistics* 29(4).
- Chen, A. Y. and Velikov, M. (2023). Zeroing in on the expected returns of anomalies. *Journal
  of Financial and Quantitative Analysis* 58(3).
