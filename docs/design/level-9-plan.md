# Plan — Level 9: tax regimes beyond Italy

Status: **approved 2026-11-15.** This list is now Level 9 of `docs/ROADMAP.md`. Every phase still gets its own design note, approved before any code, and
every rule is checked against the law in force, with sources, as 8.6 was.

## Why this level

qrlab is meant for anyone, not only for an Italian investor. Today the only tax that is
modelled in detail is Italian (`qrlab.tax.italy`, phase 8.6), and two places assume it:

- **The report kind** has one `[parameters.tax]` table, with Italian keys (`regime` is
  amministrato or dichiarativo, plus the public-bond shares).
- **Projections and backtests** have a generic `TaxModel`: a gains rate, a wealth-tax rate
  and the Italian loss rules of 8.6b.

Taxes differ from country to country in ways that change the numbers, not only the rate.
A first look, to be checked in each phase's note:

| | Italy (done) | Switzerland, private investor | Germany |
|---|---|---|---|
| Capital gains | 26 %, ETF gains are capital income | **tax-free** on private wealth (LIFD art. 16 cpv. 3), unless the investor counts as a professional trader (ESTV Circular 36, five safe-haven criteria) | 25 % + 5.5 % solidarity surcharge (26.375 %), church tax optional |
| Fund income | taxed when paid | dividends and interest are income at the marginal rate; an **accumulating** fund's reinvested income is taxed every year (ESTV price list) | **Teilfreistellung**: 30 % of an equity fund's income and gains is exempt (15 % mixed); a yearly **Vorabpauschale** on accumulating funds (base rate set each year, 3.20 % for 2026) |
| Losses | balance by year, four years, not against fund gains | irrelevant (gains are not taxed) | pots: share losses only against share gains; carried forward without a time limit |
| Allowance | none | none | Sparer-Pauschbetrag 1,000 € (2,000 € joint) |
| Withholding | 26 % by an amministrato broker | 35 % Swiss withholding tax, refundable when declared | by the German bank |
| Wealth | stamp duty, IVAFE (not modelled) | cantonal wealth tax on the year-end value | none |
| Cost basis | average cost | (not needed for gains) | **FIFO** |

"European" has no single tax law. Each EU country has its own, so the plan adds countries one
at a time, plus a simple model you configure for the others.

## Phases

### 9.1 Tax regimes as a common shape — 8–12 h

- **A common interface.** `qrlab.tax` gets one interface for every country. Its result has
  the same tables everywhere:
  - taxable events with their rule;
  - balances carried to later years;
  - yearly items (wealth tax, deemed income);
  - the tax due against the tax withheld;
  - the rules' sources and the date they were checked.
- **Italy moves behind it** unchanged: Italian reports stay byte-identical.
- **The report kind** gets `[parameters.tax] country = "it" | ...`, each country with its own
  keys, all required and none guessed.
- **Projections and backtests:** `TaxModel` presets per country, from the same rules.

### 9.2 Switzerland, private investor — 12–18 h

- **Gains:** tax-free, but the report checks the five ESTV safe-haven criteria against your
  transactions and says which are met. Some of them need inputs only you can give, such as
  your income. When the criteria are not met, it says the investor may count as a
  professional trader: analytics, not a ruling.
- **Income:**
  - dividends and interest, at a marginal rate you state, because it depends on canton,
    municipality and income;
  - an accumulating fund's yearly taxable income, from the ESTV price-list values you supply.
- **35 % withholding tax:** shown as refundable when declared.
- **Wealth tax:** a cantonal rate you state, on the year-end value.
- **Projections:** gains rate 0 and the wealth-tax rate, which `TaxModel` already supports.
  Income taxed at the marginal rate needs a new term, designed in this phase's note.
- **Report language:** in Switzerland reports in Italian (Ticino) and English work; German
  and French are in IDEAS.

### 9.3 A configurable model for other countries — 6–10 h

A model you set up with:

- a gains rate;
- a dividend rate;
- whether losses offset gains in the same year, and for how many years they carry;
- an exempt holding period;
- an annual wealth-tax rate.

It is labelled everywhere as "a simplified model you configure, not a country's law". It
covers a reasonable first view for any country not modelled in detail.

### 9.4 Germany — 20–30 h (if you want an EU country in detail)

- Abgeltungsteuer with the solidarity surcharge, and church tax as an option.
- Teilfreistellung by fund type, which needs a new instrument field.
- The yearly Vorabpauschale, with each year's base rate and its source.
- The Sparer-Pauschbetrag and the two loss pots.
- **FIFO cost basis.** This is the largest piece: the ledger today keeps the average cost of
  the Italian amministrato regime, and FIFO lots are in IDEAS.

## Order and choices

- **9.1 first:** without the common shape, each new country would copy Italy's code.
- **Then 9.2 Switzerland,** which you named, then 9.3. Germany (9.4) only if you want an EU
  country in detail. It could be another country you care about instead: France, Spain, the
  Netherlands each have different rules again.
- **Effort:** 26–40 h without Germany; 46–70 h with it.

## Risks

- **Rules change.** Each country records the date its rules were checked, as Italy does, and
  the report shows it.
- **Personal circumstances.** The marginal income rate, canton and church membership are
  inputs you state, never assumptions.
- **Scope.** Each country is its own phase with its own hand-calculated tests. No country is
  half-modelled: one that is not done in detail stays on the configurable model.

## First-look sources (checked again in each phase)

- **Switzerland:**
  - LIFD/DBG (SR 642.11) art. 16 cpv. 3, gains on private wealth;
  - ESTV, "Gains en capital sur la fortune privée";
  - ESTV Circular No. 36 of 27 July 2012 (professional securities trading), as summarised by
    cantonal and professional sources.
- **Germany:**
  - InvStG § 18 (Vorabpauschale) and § 20 (Teilfreistellung);
  - EStG § 32d (Abgeltungsteuer);
  - EStG § 20 (9) (Sparer-Pauschbetrag);
  - BMF letter of 13 January 2026: base rate 3.20 % for 2026.
