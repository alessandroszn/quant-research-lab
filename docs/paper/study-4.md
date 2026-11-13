# Study 4: rebalancing for a EUR ETF investor

*Research analytics, not investment or tax advice. Index and constructed-bond returns stand in
for ETFs.*

## Question and hypotheses

A euro investor holds world equity and euro government bonds in fixed target weights. How
often, and by which rule, should the portfolio be rebalanced once trading costs, Italian
capital-gains tax and unhedged currency are counted?

Rebalancing is mainly risk control. It keeps the portfolio near the risk the investor chose.
Each trade costs fees and, when it sells a gain, tax. The question is the trade-off between
staying near the target and paying for it.

Three hypotheses were fixed in the design note before any result was seen:

- **H1 (bands).** A 5-point band keeps the equity weight as close to target as quarterly
  rebalancing (mean absolute deviation not larger), with lower costs plus taxes paid.
- **H2 (taxes).** Monthly rebalancing ends with less after-tax wealth than annual rebalancing.
- **H3 (risk control, not return).** Buy-and-hold ends with more after-tax wealth than annual
  rebalancing, but with more risk: a higher final equity weight, higher volatility and a
  deeper maximum drawdown.

Each hypothesis is judged on the simulated paths. It counts as supported if its stated
direction holds in at least two thirds of them. For H1 and H3, every condition must hold.
This rule was also fixed in advance.

## Data and specification

**Assets.** All returns are monthly and in euros. The sample runs from {{ s4_start }} to
{{ s4_end }}, {{ s4_months }} months with no gaps and nothing forward-filled.

- *World equity, unhedged.* The Ken French Developed market return (market excess return plus
  the risk-free rate, in USD), converted to euros at the ECB reference rate of each month end.
  It stands in for an MSCI World ETF before fees.
- *Euro government bonds.* A constructed 7-year AAA zero-coupon bond, rolled monthly. Its
  return comes from the ECB's continuously compounded 6- and 7-year AAA spot rates. It stands
  in for a euro government 5–10 year ETF, but the AAA curve is less risky than a broad euro
  government index.

The raw files are stored unchanged with their checksums; the appendix lists them.

**Investor.** EUR 100,000 is invested once, with no contributions or withdrawals. The main
specification holds 60 % equity and 40 % bonds. An 80/20 portfolio is the robustness case.

**Costs.** Two scenarios: low, 0.05 % of the amount traded plus EUR 2 per trade; high, 0.20 %
plus EUR 10.

**Tax.** Realised gains are taxed at 26 %, with average cost per asset. Losses never offset
gains, as for Italian ETF holders. At the end, each asset's unrealised gain is taxed at the
same rate, as if everything were sold. Every policy is therefore compared after all taxes, and
deferral is valued correctly.

**Policies.** Seven rules, fixed in advance:

| Policy | Rule |
|---|---|
| Buy-and-hold | never rebalance |
| Monthly, Quarterly, Annual | rebalance to target every month, quarter or year; annual is the reference |
| Band 5, Band 10 | when a weight is more than 5 (10) points from target, trade back to target |
| Band 5, edge | 5-point band, but trade only back to the band's edge |

The rules look at the drifted weights at each month end and trade at that month's close. They
use only information known at that point.

**Two designs.** On the *historical path*, every policy runs on the actual monthly returns.
This is one path and a descriptive case. In the *simulation*, a stationary bootstrap resamples
the joint equity and bond returns in blocks of about 12 months. It draws 2,000 paths of 240
months (20 years) with a fixed seed. Every policy runs on the same paths and is compared with
annual rebalancing path by path. The trial ledger records {{ s4_tried }} configurations: 60/40
and 80/20.

## Historical results

The table gives every policy on the historical path, 60/40 and low costs. Deviation is the
mean absolute distance of the equity weight from 60 %, in percentage points.

```{include} _generated/s4_historical.md
```

Buy-and-hold ends with the most after-tax wealth, {{ s4_h_bh_wealth }}, against
{{ s4_h_annual_wealth }} for annual rebalancing. It gets there by drift. Its equity weight
ends at {{ s4_h_bh_final_eq }} and is {{ s4_h_bh_dev }} away from target on average, against
{{ s4_h_annual_dev }} for annual rebalancing. Its volatility is {{ s4_h_bh_vol }}, against
{{ s4_h_annual_vol }}. It also leaves the largest tax bill at the end: {{ s4_h_bh_deferred }},
against {{ s4_h_annual_deferred }}.

Monthly rebalancing ends with the least, {{ s4_h_monthly_wealth }}. It makes
{{ s4_h_monthly_trades }} trades, against {{ s4_h_annual_trades }} for annual rebalancing. Its
trading costs are small, {{ s4_h_monthly_costs }}. Its taxes paid along the way are not:
{{ s4_h_monthly_taxes }}, against {{ s4_h_annual_taxes }}. In return its volatility is
{{ s4_h_monthly_vol }}, barely below annual rebalancing.

Quarterly rebalancing ends with {{ s4_h_quarterly_wealth }}. The lazier rules end above
annual rebalancing: {{ s4_h_band5_wealth }} for the 5-point band, {{ s4_h_band10_wealth }}
for the 10-point band and {{ s4_h_edge_wealth }} for the 5-point band to the edge. The
ordering is therefore: buy-and-hold first, then the bands, then annual, quarterly and monthly
rebalancing. One path cannot tell whether this ordering is robust. The simulation addresses
that.

## Simulated results

The table gives the paired difference of each policy against annual rebalancing over 2,000
paths of 20 years, 60/40 and low costs. The wealth difference is the median with its 5 % and
95 % quantiles. "Ahead" is the share of paths in which the policy ends with more
after-tax wealth than annual rebalancing. The other columns are median paired differences.

```{include} _generated/s4_simulated.md
```

**The reference.** Annual rebalancing ends with a median after-tax wealth of
{{ s4_s_annual_wealth }}, with a 5–95 % range from {{ s4_s_annual_p05 }} to
{{ s4_s_annual_p95 }}. It makes a median of {{ s4_s_annual_trades }} trades, pays
{{ s4_s_annual_taxes }} of tax along the way and leaves {{ s4_s_annual_deferred }} at the end.

**Frequent rebalancing.** Monthly rebalancing ends with a median {{ s4_s_monthly_diff }} less
than annual rebalancing. The 5–95 % range of that shortfall runs from {{ s4_s_monthly_p95 }}
to {{ s4_s_monthly_p05 }}: it never turns into a gain in that range. Monthly rebalancing is
ahead in only {{ s4_s_monthly_share }} of paths. It pays a median {{ s4_s_monthly_ct }} more
in costs and taxes, for {{ s4_s_monthly_trades }} trades. In exchange, volatility is only
{{ s4_s_monthly_vol }} lower. Quarterly rebalancing lies in between: a median
{{ s4_s_quarterly_diff }} less, ahead in {{ s4_s_quarterly_share }} of paths, with
{{ s4_s_quarterly_ct }} more in costs and taxes.

**Bands.** The 5-point band trades much less than quarterly rebalancing: a median of
{{ s4_s_band5_trades }} trades in 20 years, against {{ s4_s_quarterly_trades }}. It pays
{{ s4_s_band5_ct }} less in costs and taxes than annual rebalancing. But it stays further
from target than quarterly rebalancing: its median deviation is {{ s4_s_band5_dev }}, against
{{ s4_s_quarterly_dev }} for quarterly and {{ s4_s_annual_dev }} for annual rebalancing. It
behaves like annual rebalancing, not like quarterly. Its median gain over annual rebalancing
is {{ s4_s_band5_diff }}, with a 5–95 % range from {{ s4_s_band5_p05 }} less to
{{ s4_s_band5_p95 }} more. It is ahead in {{ s4_s_band5_share }} of paths.

The wider or lazier rules end with more. The 10-point band is a median {{ s4_s_band10_diff }}
ahead, in {{ s4_s_band10_share }} of paths. The 5-point band to the edge is
{{ s4_s_edge_diff }} ahead, in {{ s4_s_edge_share }} of paths. Part of this is deferred tax.
Mainly, these rules let equity drift above target. Their median deviation is
{{ s4_s_band10_dev }} and {{ s4_s_edge_dev }} larger than annual rebalancing. Their median
final equity weights are {{ s4_s_band10_final_eq }} and {{ s4_s_edge_final_eq }}. Part of the
extra wealth is extra risk, not free return.

**Buy-and-hold.** It ends a median {{ s4_s_bh_diff }} ahead of annual rebalancing. The 5–95 %
range runs from {{ s4_s_bh_p05 }} less to {{ s4_s_bh_p95 }} more. Its equity weight drifts to
a median of {{ s4_s_bh_final_eq }}, and its deviation from target is {{ s4_s_bh_dev }} larger.
Its volatility is {{ s4_s_bh_vol }} higher, and its maximum drawdown {{ s4_s_bh_dd }} deeper.
It leaves a median tax bill of {{ s4_s_bh_deferred }} at the end. It has become a different,
riskier portfolio.

**Verdicts, 60/40.**

- **H1 is not supported.** The band pays less in costs and taxes than quarterly rebalancing in
  {{ s4_h1_cost }} of paths. But its deviation is not larger in {{ s4_h1_dev }} of them. The
  hypothesis compared the band with the wrong calendar.
- **H2 is supported.** Monthly rebalancing ends with less after-tax wealth than annual
  rebalancing in {{ s4_h2 }} of paths.
- **H3 is supported.** Buy-and-hold ends with more after-tax wealth in {{ s4_h3_wealth }} of
  paths. It has a higher final equity weight in {{ s4_h3_eq }}, higher volatility in
  {{ s4_h3_vol }} and a deeper maximum drawdown in {{ s4_h3_dd }}.

## Statistical and economic significance

**Statistical.** The study reports no p-values. The two-thirds rule is a summary rule fixed in
advance, not a significance test. All paths come from one resampled history, {{ s4_start }} to {{ s4_end }}.
The shares therefore measure how stable a ranking is when that history is reshuffled in
blocks. They do not measure uncertainty about a different future. The comparisons are paired:
every policy sees the same returns, so common market noise cancels. That is why a ranking can
hold in nearly every path even when wealth levels vary widely. The specification search was
small. Policies, costs, tax, block length, horizon and the two-thirds rule were fixed before
the run, and the ledger counts {{ s4_tried }} configurations.

**Economic.** Three points stand out.

- Taxes, not trading costs, drive the differences. On the historical path, monthly
  rebalancing pays {{ s4_h_monthly_costs }} in costs but {{ s4_h_monthly_taxes }} in taxes
  along the way. With 26 % on realised gains and no loss offset, frequent selling of winners
  is expensive.
- The cost of rebalancing too often is real but modest. Monthly rebalancing gives up a median
  {{ s4_s_monthly_diff }} over 20 years and buys almost no extra risk control.
- The differences between reasonable rules are small next to the range of outcomes. Annual
  rebalancing alone ends anywhere between {{ s4_s_annual_p05 }} and {{ s4_s_annual_p95 }} in
  90 % of paths. The median gap between annual rebalancing and the 5-point band is
  {{ s4_s_band5_diff }}.

Rebalancing is worth what the investor values staying near the chosen mix. The extra wealth
of buy-and-hold and of the lazier bands comes with more equity risk. It is not a free gain.

## Robustness

**High costs.** With the high cost scenario the ranking is the same and the gaps widen.
Monthly rebalancing ends a median {{ s4_s_monthly_diff_high }} below annual rebalancing, and
quarterly {{ s4_s_quarterly_diff_high }} below. The verdicts do not change. For H1 the band's
deviation is not larger in {{ s4_h1_dev_high }} of paths, while its costs and taxes are lower
in {{ s4_h1_cost_high }}. H2 holds in {{ s4_h2_high }} of paths and buy-and-hold ends richer in
{{ s4_h3_wealth_high }}.

**80/20 portfolio.** The verdicts are the same. For H1, the band's deviation is not larger
in {{ s4_r_h1_dev }} of paths, though its costs and taxes are lower in {{ s4_r_h1_cost }}.
Monthly rebalancing ends with less than annual rebalancing in {{ s4_r_h2 }} of paths, by a
median {{ s4_r_monthly_diff }}. Buy-and-hold ends richer in {{ s4_r_h3_wealth }} of paths, by
a median {{ s4_r_bh_diff }}. It has a higher final equity weight in {{ s4_r_h3_eq }}, higher
volatility in {{ s4_r_h3_vol }} and a deeper drawdown in {{ s4_r_h3_dd }}. The bands are ahead
of annual rebalancing in {{ s4_r_band5_share }} (5-point), {{ s4_r_band10_share }} (10-point)
and {{ s4_r_edge_share }} (5-point to the edge) of paths.

**Historical path.** The 80/20 historical path gives the same picture as the 60/40 one.
Buy-and-hold ends with {{ s4_r_h_bh_wealth }}, annual rebalancing with
{{ s4_r_h_annual_wealth }} and monthly rebalancing with {{ s4_r_h_monthly_wealth }}.

**Limitations.**

- *Proxies.* Index and constructed-bond returns are not ETF returns. There are no fund fees
  or tracking difference, which would be roughly equal across policies.
- *One history.* The bootstrap resamples a single period: rates mostly falling, then rising
  sharply, and strong equity returns. Long equity drawdowns or years of positive equity–bond
  correlation could change the ranking.
- *Tax simplified.* One 26 % rate; the 12.5 % rate on the government-bond share is ignored,
  as are stamp duty and loss carry-forward.
- *Trading at the observed close.* The rules see month-end weights and trade at that close.
- *No contributions.* With regular savings, new money can rebalance without selling. That
  would favour rules that use flows.

The [full report](../studies/04-rebalancing.md) gives every table, the data provenance and
the full discussion.
