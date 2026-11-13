# Study 4 — Rebalancing for a EUR ETF investor

Run on 2026-11-12 with Ken French and ECB data of the same day. The design note was approved
before any result was seen: [`docs/design/5.3-study-4-rebalancing.md`](../design/5.3-study-4-rebalancing.md).

*Research analytics, not investment or tax advice. Index and constructed-bond returns stand in
for ETFs.*

*Re-run on 2026-11-13 from a clean checkout of commit 63f808a, with the same data: every
output was byte-identical.*

## 1. Question and hypotheses

A euro investor holds world equity and euro government bonds in fixed target weights. How often,
and by which rule, should the portfolio be rebalanced once costs, Italian capital-gains tax (26 %
on realised gains, no offset of losses) and unhedged currency are counted?

The hypotheses were fixed before running. Each is judged on the simulated paths: it is supported
if its stated direction holds in at least two thirds of them.

- **H1.** A 5-point band keeps the equity weight as close to target as quarterly rebalancing
  (mean absolute deviation not larger), with lower costs plus taxes.
- **H2.** Monthly rebalancing ends with less after-tax wealth than annual rebalancing.
- **H3.** Buy-and-hold ends with more after-tax wealth than annual rebalancing, but with more
  risk: a higher final equity weight, higher volatility and a deeper maximum drawdown.

## 2. Data and assumptions

**Assets (EUR, monthly, October 2004 to September 2026, 264 months):**

- **World equity, unhedged:**
  - Ken French Developed market (Mkt-RF + RF, USD);
  - converted to EUR at the last ECB reference rate of each month;
  - 10.4 % a year on average, volatility 13.1 %.
- **Euro government bonds:**
  - a 7-year AAA zero-coupon bond, rolled monthly;
  - built from the ECB's continuously compounded 6- and 7-year spot rates;
  - 2.8 % a year, volatility 4.9 %.
- The correlation between the two is 0.04.

**Files**, downloaded 2026-11-12 and stored unchanged in the git-ignored raw store (Ken French
and ECB, used with citation and not redistributed):

| File | Bytes | SHA-256 |
|---|---:|---|
| `Developed_3_Factors_CSV.zip` (Ken French) | 4,975 | `3f99cfdeddd1914e3d8f84ce51d775aeed3e98ed0c290957e88f4df9912f8a23` |
| `eurofxref-hist.zip` (ECB reference rates) | 643,073 | `1388fe0047cbe5c08b009e6ccc5e1e344f08e6011f1c1bf8d4a2a7cf333d3078` |
| `YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_6Y` (ECB, CSV) | 3,161,126 | `650da8ebc5d943ae5ca6a24fefe829af0539db71407b05fd95d0824c3aa3198d` |
| `YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_7Y` (ECB, CSV) | 3,160,810 | `231b2ca19078a3e0e0212b6242820e41e947b199c80b280efb8c3fc3ea7781e2` |

The sample ends in September 2026, the last month of the Ken French file. Nothing is
forward-filled, and every month has an observation.

**Investor:**

- €100,000 invested once, with no contributions or withdrawals.
- **Main specification:** 60 % equity and 40 % bonds. **Robustness:** 80/20.

**Costs, two scenarios:**

- low: 0.05 % of the amount traded plus €2 per trade;
- high: 0.20 % plus €10.

**Tax:**

- 26 % on realised gains, average cost per asset, losses never offset gains;
- at the end, the same rate on each asset's unrealised gain, as if everything were sold. Each
  policy is therefore valued after all taxes.

## 3. Specification

**The seven policies:**

| Policy | Rule |
|---|---|
| Buy-and-hold | never rebalance |
| Calendar | rebalance to target every month, quarter or year (annual is the reference) |
| 5- and 10-point bands | when a weight leaves its band, trade back to target |
| 5-point band, to the edge | when a weight leaves the band, trade only back to its edge |

**How the policies run:**

- The rules look at the drifted weights at each month end and trade at that close.
- **Historical path:** every policy runs on the actual 264 months.
- **Simulation:**
  - 2,000 stationary-bootstrap paths of 240 months (20 years), resampling the joint monthly
    returns in blocks of about 12 months, with seed 20261112;
  - every policy runs on the same paths and is compared with annual rebalancing path by path;
  - the trial ledger records 2 configurations.

**Reproduce:**

```bash
uv run qrlab run configs/studies/rebalancing_60_40.toml
uv run qrlab run configs/studies/rebalancing_80_20.toml
```

## 4. Results (60/40, low costs unless stated)

### Historical path, October 2004 to September 2026

| Policy | After-tax wealth | After-tax return p.a. | Volatility | Max drawdown | Mean \|equity − 60 %\| | Final equity | Trades | Costs | Taxes paid | Tax at the end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Buy-and-hold | €439,857 | 6.96 % | 9.04 % | −27.9 % | 9.6 pts | 87.2 % | 0 | €0 | €0 | €119,409 |
| Monthly | €350,631 | 5.87 % | 8.11 % | −28.2 % | 0.0 pts | 60.0 % | 528 | €1,456 | €39,654 | €43,953 |
| Quarterly | €363,481 | 6.04 % | 8.19 % | −27.6 % | 0.7 pts | 60.0 % | 176 | €632 | €34,217 | €53,332 |
| **Annual** | **€366,640** | **6.08 %** | **8.17 %** | **−26.3 %** | **2.0 pts** | **60.0 %** | **44** | **€240** | **€25,170** | **€63,921** |
| Band 5, to target | €373,842 | 6.18 % | 8.16 % | −27.6 % | 2.0 pts | 62.3 % | 24 | €201 | €24,564 | €67,280 |
| Band 10, to target | €391,412 | 6.40 % | 8.41 % | −28.3 % | 4.3 pts | 62.3 % | 10 | €161 | €25,929 | €71,519 |
| Band 5, to the edge | €390,164 | 6.38 % | 8.35 % | −26.9 % | 3.8 pts | 65.0 % | 170 | €467 | €22,985 | €74,372 |

### Simulation: 2,000 paths of 20 years, differences against annual rebalancing

The table gives the after-tax wealth difference (median and 5–95 % range), the share of paths
where the policy beats annual rebalancing, and the median differences in equity deviation,
costs plus taxes paid, volatility and maximum drawdown.

| Policy | Wealth difference, median [5 %, 95 %] | Paths ahead | Equity deviation | Costs + taxes paid | Volatility | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Buy-and-hold | +€56,087 [−€12,038, +€315,231] | 84 % | +13.3 pts | −€20,935 | +1.7 pts | −4.3 pts |
| Monthly | −€14,384 [−€32,317, −€4,979] | 0.1 % | −1.8 pts | +€13,018 | −0.1 pts | −1.1 pts |
| Quarterly | −€7,148 [−€19,170, −€133] | 4.7 % | −1.2 pts | +€5,736 | −0.0 pts | −0.6 pts |
| Band 5, to target | +€2,969 [−€5,432, +€12,123] | 72 % | +0.2 pts | −€1,452 | +0.1 pts | −0.5 pts |
| Band 10, to target | +€13,297 [−€2,779, +€39,142] | 90 % | +2.2 pts | −€4,149 | +0.2 pts | −0.5 pts |
| Band 5, to the edge | +€12,248 [−€438, +€36,910] | 94 % | +1.8 pts | −€4,054 | +0.2 pts | −0.4 pts |

**Medians for annual rebalancing:**

- after-tax wealth €333,109, with a 5–95 % range of €189,379 to €562,280;
- 40 trades;
- €20,697 of tax paid along the way and €57,446 at the end.

With high costs, the ranking is the same and the gaps widen: monthly rebalancing is
−€21,773 against annual.

### Hypotheses

The share is the fraction of the 2,000 paths in which the stated direction holds, at low
(high) costs.

| | Condition | 60/40 | 80/20 | Verdict |
|---|---|---:|---:|---|
| **H1** | Band 5 deviates no more than quarterly | 0 % (0 %) | 0 % (0 %) | **not supported** |
| | Band 5 pays less cost + tax than quarterly | 98.6 % (99.4 %) | 99.9 % (99.9 %) | |
| **H2** | Monthly ends with less wealth than annual | 99.9 % (100 %) | 99.9 % (100 %) | **supported** |
| **H3** | Buy-and-hold ends with more wealth | 84.1 % (84.9 %) | 82.7 % (84.0 %) | **supported** |
| | … with a higher final equity weight | 96.6 % | 96.6 % | |
| | … with higher volatility | 94.2 % | 93.4 % | |
| | … with a deeper maximum drawdown | 85.2 % | 85.9 % | |

## 5. Conclusions

- **H1 is not supported.** The 5-point band trades much less than quarterly rebalancing: 22
  trades in 20 years against 160. It pays less in costs and taxes in 98.6 % of paths, by about
  €7k (against annual: −€1.5k for the band, +€5.7k for quarterly). But it
  stays further from target in every path (2.0 points against 0.6). It behaves like **annual**
  rebalancing, with about the same deviation and slightly less tax, not like quarterly. The
  hypothesis compared it with the wrong calendar.
- **H2 is supported.** Rebalancing every month costs about €14k after tax over 20 years against
  annual rebalancing (median, low costs; €22k with high costs). It loses in 99.9 % of paths, and
  buys almost no extra risk control: volatility is 0.1 points lower. With 26 % on realised gains
  and no loss offset, frequent selling of winners is expensive.
- **H3 is supported.** Buy-and-hold ends richer in 84 % of paths (median +€56k). It does so by
  letting equity grow from 60 % to about 86 %: in effect it becomes a different, riskier
  portfolio, with 1.7 points more volatility and drawdowns 4.3 points deeper. It also leaves the
  largest tax bill at the end (€102k median).
- **Overall:**
  - Rebalancing is risk control, and here it is worth only what the investor values staying near
    60/40.
  - Among rebalancing rules, the wider or lazier ones (10-point band, 5-point band to the edge)
    end with more wealth than annual rebalancing in about 90 % of paths. Partly this is deferred
    tax, but mainly they let equity drift above target. Part of the extra wealth is therefore
    extra risk, not free return.
  - The differences between reasonable rules are small next to the range of outcomes: the 5–95 %
    range of annual rebalancing alone runs from €189k to €562k.
  - The historical path and the 80/20 portfolio give the same picture.

## 6. Limitations

- **Proxies:**
  - Ken French Developed market returns and a constructed AAA zero, not ETFs, so there are no
    fund fees or tracking difference (equal across policies).
  - The AAA curve is less risky than a broad euro government bond index.
- **One history:** the bootstrap resamples 2004–2026, a period with mostly falling then sharply
  rising rates and strong equity returns. Other regimes, for example long equity drawdowns or
  equity–bond correlation above zero for years, could change the ranking.
- **Tax simplified:**
  - one 26 % rate, with government-bond ETFs' 12.5 % share ignored;
  - stamp duty ignored;
  - no loss carry-forward;
  - not tax advice.
- **Trading at the observed close:** the rules see month-end weights and trade at that close.
- **No contributions:** with regular savings, new money can rebalance without selling, which
  would favour rules that use flows. This is recorded as an idea.

## References

- Kenneth R. French Data Library: Developed market factors.
- European Central Bank: euro foreign exchange reference rates; euro area yield curves (AAA,
  Svensson model, continuous compounding).
- Daryanani, G. (2008). Opportunistic rebalancing: a new paradigm for wealth managers. *Journal
  of Financial Planning* 21(1).
