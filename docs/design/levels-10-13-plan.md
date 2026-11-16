# Plan — Levels 10 to 13: publication, a complete report, a usable app, deeper research

Status: **approved 2026-11-16.** These four levels are now Levels 10 to 13 of
`docs/ROADMAP.md`.
Every phase still gets its own design note, approved before any code.

## Why these levels

Levels 8 and 9 are done, and the roadmap has nothing after them. The owner chose all four
open themes. Each one is a level of its own, with a milestone, because they share no code:

| Level | Theme | Milestone | Indicative hours |
|---|---|---|---|
| 10 | Publication | **M10 v1.0 public** | 12–22 |
| 11 | A complete portfolio report | **M11 Complete report** | 30–48 |
| 12 | A usable app | **M12 App 1.x** | 36–52 |
| 13 | Deeper research | **M13 Research 2** | 38–56 |

Total: 116–178 h. The items come from `docs/IDEAS.md`; those not listed here stay there.

## Order and why

1. **Publication first.** `main` is 92 commits past the last green CI run (`e729101`,
   2026-11-13), and none of them ran on Linux, because the private repository's Actions
   minutes ran out that day. The batch grows with every phase. A public repository runs
   standard GitHub-hosted runners at no cost, so publishing also brings CI back for every
   later level. Nothing in it changes results.
2. **Then the report (11),** because it is a matter of correctness, not polish: today the risk
   section of a distributing fund ignores its distributions.
3. **Then the app (12),** which shows the report: better to polish it once the report is
   complete.
4. **Research last (13):** it is independent of the rest, the largest, and nothing waits for
   it.

Each level ends in a release (1.0.0, 1.1.0, 1.2.0, 1.3.0), cut by the owner as
`docs/project/releasing.md` describes.

## Level 10 — Publication → M10 v1.0 public

### 10.1 The Linux check, locally — 3–6 h

CI must pass before the repository becomes public, but CI has no minutes. Two ways:

- **A Linux environment on this PC** (recommended): WSL 2 is enabled here but has no
  distribution. With an Ubuntu distribution, installed by the owner, the quality gate runs on
  Linux with Python 3.11 and 3.13, as CI does.
- **Or wait** for the monthly minutes to come back and push `main` then.

Whatever Linux finds is fixed on branches, each with a regression test.

### 10.2 Ready to be read by others — 4–8 h

- `scripts/audit_history.py` over the whole history, pointed at `data/`: it must end with
  `CLEAN`.
- **Stale text:** README, ROADMAP status lines, the version (`1.0.0rc1` today), the guides'
  screenshots (synthetic data only), the data-sources table with every terms decision.
- **The disclaimer:** every report and the README say they are analytics, not investment
  advice. Checked, not assumed.

### 10.3 Release 1.0.0 — 5–8 h

As `docs/project/releasing.md`:

1. the owner pushes `main` and does the one-time setup (visibility, environments, trusted
   publishers, Zenodo, Pages);
2. `v1.0.0rc1` goes to TestPyPI and is installed in a clean environment;
3. then `v1.0.0` goes to PyPI, with the docs and the Windows installer.

Every step that publishes or changes a setting is the owner's, on their accounts, as before.

## Level 11 — A complete portfolio report → M11 Complete report

### 11.1 Total returns for distributing funds — 8–12 h

- **The gap:** the report's risk section and the diversification checks read price returns.
  For a distributing fund these miss every distribution, so its volatility looks the same
  but its return looks lower, and correlations are slightly off.
- **The change:** an optional total-return series per fund, or its distributions, which the
  report uses for risk and the checks. Valuation still uses prices.
- **When neither is given,** the report says so for each distributing fund, instead of
  silently using price returns.

### 11.2 A benchmark in the report — 6–10 h

- A benchmark series as an input of the report kind, in its own currency, converted with
  dated FX like every other series.
- Relative measures on the same dates: active return, tracking error, information ratio,
  beta, each with its convention stated.
- Beta on excess returns over the €STR, from 8.5.

### 11.3 Italian stamp duty and IVAFE — 6–10 h

- **Imposta di bollo** on financial products held with an Italian intermediary, and **IVAFE**
  on those held abroad (the dichiarativo regime): rate, base, days held in the year, and
  minimums.
- Checked against the law in force, with sources and the date checked, as 8.6 was.
- They go in the Italian tax section as yearly items, a slot 9.1 already gives every regime.

### 11.4 VaR backtest and factor proxies in the report — 6–10 h

- **The VaR backtest** (Kupiec and Christoffersen, already in the `risk_report` kind) in the
  report's risk section, with the number of observations it needs.
- **Factor proxies** for positions without their own long history, so that factor shocks and
  older crises cover them, as `scenario_analysis` already does. Labelled as proxies.

### 11.5 Small open items — 4–6 h

- `[parameters]` keys for the loss rules (`LossRules`) in the backtest, projection and
  report kinds.
- `income_tax_rate` and `taxable_yield` in the standalone `projection` kind, as in the
  report.
- A full table of Italian country names, so that iShares' Italian files need no list per
  fund.

## Level 12 — A usable app → M12 App 1.x

The rule stays: the app contains no financial logic. Everything below that knows about
finance goes into `qrlab.experiments`, and the app only shows it.

### 12.1 A form for each analysis — 14–20 h

- **Parameter schemas** in the kinds (`qrlab.experiments`): every key with its type, unit,
  allowed values, whether it is required, and a help text. The schema becomes the single
  source for validation, the docs and the form.
- **The app** builds a form from the schema, instead of the TOML editor. The TOML stays
  available, and the two always agree, because the form writes the same config.

### 12.2 Cancelling a run, and a queue — 8–12 h

- A cancellation hook in the runner, checked between steps. A cancelled run leaves no
  partial results that look complete.
- A queue in the app: runs one after another, each with its state.

### 12.3 Interactive charts — 8–12 h

- Zoom, pan and the value under the cursor, through Matplotlib's Qt backend: no new
  dependency.
- The runner already writes the data behind each figure; the app plots those files and
  never recomputes them.

### 12.4 PDF export and an icon — 6–8 h

- **PDF of a report,** from the app. Options to compare in the note: Qt's own PDF writer,
  already in PySide6, or a new dependency. A dependency needs its reason recorded, as always.
- **An app icon** for the window and the installer.

Code signing costs money and stays in IDEAS until the owner decides.

## Level 13 — Deeper research → M13 Research 2

### 13.1 Inference across many strategies — 10–14 h

- **Romano-Wolf stepdown:** family-wise error control that uses the dependence between
  strategies.
- **The studentized bootstrap** for Sharpe-ratio differences (Ledoit and Wolf, 2008), which
  has better size in small samples.
- Cross-checked on cases with known answers and against independent implementations where
  one exists.

### 13.2 Fama-MacBeth regressions — 10–14 h

- Cross-sectional regressions each period, with Newey-West standard errors and the Shanken
  correction for estimated betas.
- Cross-checked against statsmodels on synthetic panels whose true premia are known.

### 13.3 Daily international factors — 4–6 h

- Ken French's daily Developed and Europe factors (only monthly and annual are parsed today),
  under the terms already recorded for that source.

### 13.4 The factor-zoo study, again — 14–22 h

- Romano-Wolf on the zoo, next to the existing corrections.
- Time effects in the decay regression (month fixed effects or a trend), McLean and
  Pontiff's robustness check.
- Decay by category (accounting, price, analyst).
- An honest write-up: what changes and what does not, null results included.

The trading costs of anomalies (Chen and Velikov's cost data) stay in IDEAS until their terms
are checked.

## Not in these levels

These stay in `docs/IDEAS.md`:

- Germany in detail, and other countries in detail;
- Italian taxes on income (dividends with foreign withholding);
- code signing and a macOS build;
- a licensed price API;
- reconciliation with a broker export.

## Risks

- **The Linux check (10.1)** may find several failures at once, after 92 commits. Each one
  gets its own fix and regression test; publication waits for all of them.
- **Publishing is one-way.** Once public, the history is public. The audit (10.2) runs over
  every version of every file, not only the current tree.
- **Scope.** Four levels is a lot. Each level is closed and reviewed before the next starts,
  and the owner can stop after any of them: each milestone is useful alone.
- **New dependencies** (PDF in 12.4 above all): each one needs a recorded reason, and the
  Qt-only option is considered first.
