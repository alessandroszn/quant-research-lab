# Plan — Level 8: the report on a real portfolio (v1.x)

Status: **draft, waiting for approval.** Once approved, this list moves into `docs/ROADMAP.md`
as Level 8, and the ideas it takes are removed from `docs/IDEAS.md`. Every phase still gets its
own design note, approved before any code.

## Why this level

The 1.0 code is complete:

- Levels 0–6 are done.
- The gap-closing phases 7.1–7.4 are merged.
- Only the release steps on GitHub are left.

It has never run on a real portfolio, though. Every example is synthetic: one EUR fund, four
monthly prices, a holdings file written by hand. Real data will differ:

- **The broker export:** its own wording, columns, and corner cases.
- **Issuer holdings files:** country names instead of ISO codes, preambles, and footers.
- **Prices:** gaps and stale values.
- **Taxes:** the Italian rules, which a single capital-gains rate does not describe.

The goal of Level 8 is **M8: the HTML report of your own portfolio, complete, correct and in
Italian, produced by the CLI and the app from files in `data/`.** It covers:

- valuation in several currencies, with look-through and tracking;
- risk, stress tests and a projection;
- a Sharpe ratio on a stated risk-free rate;
- the Italian tax position.

The rule on personal data does not change. Real files stay in the git-ignored `data/` folder.
Tests, examples, fixtures, screenshots and published reports use synthetic data only.

## Phases, in order

The order follows dependencies first, then value. Phase 8.1 may reorder the rest: what breaks
on real data is evidence, and the plan should follow it.

### 8.1 First run on the real portfolio (discovery) — 3–5 h

- **What you provide**, in `data/`:
  - the broker export;
  - price files of the funds;
  - holdings files downloaded by hand from the issuers' sites;
  - master data for each fund. I draft it with you from the KID and factsheet; nothing is
    downloaded.
- **What I do:**
  - write the private mappings in `data/`;
  - run `portfolio_report`;
  - record every failure, wrong number or missing feature.
- **Output:**
  - private run notes in `data/` (git-ignored);
  - a **public list of gaps with no personal data** ("the broker writes X", "the issuer file
    has Y"), which becomes the evidence for 8.2–8.7.
- **Checks:**
  - the report's end value and cash are reconciled with the broker's own statement on the
    same date;
  - realised gains are reconciled with the broker's tax statement. Any difference is
    explained before moving on.
- **Code:** none, unless a bug blocks the run. Bugs found get a regression test on synthetic
  data, in their own small fix.

### 8.2 Issuer holdings as published — 6–10 h

- **Country names to ISO 3166-1 alpha-2.** Issuers write "United States" or "Korea (South)",
  not `US` or `KR`.
  - A table of the official short names, plus aliases as issuers write them, with the source
    and the date it was checked.
  - An unknown name raises and names the file and line. It is never guessed.
- **Issuer map file.** A declared CSV or TOML from security ISIN to issuer, loaded and passed
  to the kind (`issuers`, today always `None`). With it, two bonds of the same issuer count as
  one issuer.
- **Mappings for the issuers you hold.** These are only for files you download by hand, with
  their terms of use reviewed and the decision recorded. There is no download code.
- **Hand test:** a synthetic file in each issuer's layout, with a known country split.

### 8.3 Risk and stress tests in the report kind — 6–8 h

- **Position returns** come from the price files the report already reads, on their own
  dates. Missing returns are never filled.
- **`RiskSummary` in the report:**
  - covariance, volatility contributions, VaR and ES;
  - an optional scenarios file, as in `scenario_analysis`.
- **Hand test:** two positions with a known covariance, giving portfolio volatility and
  contributions by hand.
- **Documented limit:** price returns of distributing funds miss the dividends (see 7.3).

### 8.4 Projection in the report kind — 5–8 h

- **Settings in `[parameters.projection]`:** horizon, engine, flows, inflation, taxes and
  sensitivity.
- **Starting point:** the current value and weights.
- **Output:** a distribution with the stated assumptions, never a single number, plus the 7.2
  notice.
- **Hand test:** the normal engine's log-normal closed form, as in the `projection` kind.

### 8.5 Risk-free rate — 4–6 h

- **An optional €STR input** (ECB, already parsed by `qrlab.data.parse_estr`), with its
  provenance.
- **Uses:**
  - a Sharpe ratio in the report on excess returns, labelled TWR-based;
  - beta on excess returns in the checks.
- **Without it:** no Sharpe ratio, and the report says why.
- **Hand test:** a constant €STR gives the same beta. A three-month excess-return Sharpe ratio
  is worked by hand.

### 8.6 Italian tax position — 10–15 h

- **Descriptive analytics, not tax advice.** The rules are stated in the note, with sources:
  TUIR articles 44, 67 and 68, and D.Lgs. 461/1997 for the *regime amministrato*. They are
  checked against the law in force when the phase starts, since the 2023 tax-reform delegation
  (L. 111/2023) may change how financial income is taxed.
- **Categories:**
  - gains on funds and ETFs are *redditi di capitale*: they are taxed in full and cannot absorb
    losses;
  - gains and losses on shares, ETCs and bonds are *redditi diversi*.
  - Losses from either can offset only *redditi diversi* gains.
- **The losses balance (*zainetto fiscale*):**
  - realised losses by year;
  - their expiry at the end of the fourth following year;
  - the part already used.
- **Rates:** 26 %, and 12.5 % on government and white-list bonds, applied by share where a fund
  reports it.
- **Reconciliation:** with the taxes the broker records in the export. A difference is shown,
  never hidden.
- **Simulation and backtest:** the same loss carry-forward goes into `TaxModel`. Today it
  overstates taxes, as IDEAS notes.
- **Hand test:** a sequence of gains and losses across five years, with expiry, worked by hand.

### 8.7 A report entirely in Italian — 4–6 h

- **Translate what is still in English:**
  - import notes;
  - the reasons why a check does not apply;
  - library messages shown in the report.
- **Total-return position returns** for the diversification checks, where a total-return
  series is available.
- **Test:** an Italian report contains no untranslated text from a known list.

**M8 — the report of a real portfolio, reconciled with the broker.** Each phase ends as a minor
version (1.1.0, 1.2.0, …), released in the weekly batches, once GitHub is available.

## Not in Level 8 (they stay in IDEAS)

- **Research ideas:** Romano-Wolf, studentized bootstrap, Fama-MacBeth, new studies.
- **App ideas:** form editor, cancelling runs, interactive charts, icon, code signing, macOS.
- **Data ideas:** `qrlab fetch` and download adapters.
- **PDF export.**

Any of them can be planned as a later level.

## Housekeeping in the same change, once approved

- `docs/ROADMAP.md`:
  - record Level 7, the gap-closing phases 7.1–7.4, which are done;
  - add Level 8 from this plan.
- `docs/IDEAS.md`:
  - remove the two rows done in 7.4: "FX inputs for the portfolio_report kind", and the
    look-through part of "Look-through, risk and projection in the portfolio_report kind";
  - remove the rows this plan takes into Level 8.

## Risks

- **Real data is personal.** Only you see the private notes and mappings, which stay in
  `data/`. Everything published is rebuilt on synthetic data. Before going public,
  `scripts/audit_history.py` runs on the real-data folder.
- **Tax rules are legal rules.** 8.6 states its sources and their date, reconciles with the
  broker, and calls itself analytics, not tax advice. If a rule is unclear, the phase stops
  and asks.
- **Scope.** That is seven phases. If 8.1 shows the report already works well enough, the
  later phases can shrink.
