# Limitations

The limitations below are those stated in the four reports, gathered here. They bound what the
results can show; none of them is corrected in this paper.

## Data

- **Revisions.** The Kenneth R. French library revises its history. Every number depends on the
  vintage downloaded for these runs (Appendix A). Studies 1 and 2 therefore differ in the
  details from the papers they replicate, even over the papers' own samples.
- **Paper portfolios.** The factors, industry and size/book-to-market portfolios and
  long-short predictor portfolios are not investable as they stand. They carry no fees, no
  market impact and no shorting costs.
- **Gross returns in study 3.** The predictor returns are gross. Many anomalies are costly to
  trade (Chen and Velikov, 2023), so the post-publication returns are an upper bound on what an
  investor could have kept.
- **Proxies in study 4.** Index and constructed-bond returns stand in for ETFs: equity from the
  developed-market factors, bonds from the ECB AAA curve. A real ETF portfolio would add fees,
  tracking error and its own currency treatment.
- **Survivorship.** The studies inherit the providers' treatment of delisted securities;
  Quant Research Lab does not check it.

## Specification

- **Fixed settings.** HAC lags, bootstrap block lengths, burn-in periods and the
  Black-Litterman settings were fixed in the design notes and not varied. Results under other
  reasonable settings may differ.
- **One history.** The simulations of study 4 resample one period of history. Its trends and
  crises shape every simulated path.
- **Simplified tax.** Study 4 models one flat rate on realised gains, with no offset of losses
  and no carry-forward. Some of these features would change the ranking of rules that sell often.
- **Trading at the observed close.** The rules of study 4 see month-end weights and trade at the
  same close. This is a mild form of optimism about execution.
- **No contributions.** With regular savings, new money can rebalance without selling. Study 4
  does not model this, and its tax results would shrink with it.
- **Publication date as a proxy.** In study 3 the post-publication period starts the January
  after the year of publication. Working papers often circulate earlier, so the measured decay
  may start late.
- **Calendar time.** Post-publication months fall mostly in recent decades. The study 3 decay
  regression has no time fixed effects, so publication cannot be fully separated from a general
  decline of anomaly returns.

## Inference

- **In-sample tests are biased upward.** Each predictor in study 3 was published because it
  looked significant, so its own-sample test is not an independent test. This is why the
  multiple-testing bars and the post-sample periods matter.
- **Correlated tests.** Predictors and factors overlap. The corrections used are valid under
  dependence (Holm, BY) or under positive dependence (BH). Effective numbers of independent
  tests are not estimated.
- **Low power.** Out-of-sample differences between Sharpe ratios are noisy. A null result in
  studies 1 and 2 means "no detectable difference with this sample", not "no difference".
