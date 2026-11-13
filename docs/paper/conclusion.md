# Conclusion

Four portfolio rules with strong in-sample support were re-examined under real-time estimation,
costs, taxes and multiple testing, each with a design fixed before the results were seen.

- **Volatility management** raises real-time net performance only for momentum.
- **Optimised portfolios** do not beat 1/N significantly.
- **Published predictors** pass a single test far more often than a corrected one, and lose
  {{ s3_decay_pp_round }} of their return after publication.
- **Rebalancing:** a taxed euro investor gains nothing from frequent rebalancing and loses
  {{ s4_s_monthly_diff }} of median wealth over 20 years by doing it monthly.

The results are limited by their data (see Limitations): paper portfolios, gross returns in study 3,
proxies for ETFs and one tax regime. What carries over beyond these four questions is the
method. Pre-specify the design, count the configurations tried, keep in-sample and
out-of-sample results apart, report frictions next to returns, and let the text be generated
from the records. Each of these steps is cheap. Together they decide whether a result can be
believed.

The code, the configs, the design notes and the full reports are published with this paper
under open licences, so every result can be checked and rerun.
