# The desktop app

The desktop app runs every analysis of the library without the command line. It is a thin layer
over the experiment runner, with no financial logic of its own. An app run and a command-line
run of the same config write identical outputs and the same `record.json`.

Start it with `qrlab-app`, which needs the `app` extra, or install the Windows program (see
{doc}`../getting-started/installation`).

## Workspaces

A workspace is a folder with four sub-folders:

| Folder | Content |
|---|---|
| `configs/` | the experiment configs (TOML) |
| `data/` | your files and the raw store; keep real data here |
| `portfolios/` | one folder per portfolio described on the Portfolios screen |
| `results/` | the outputs of every run, with their records |

On the **Home** screen, open a workspace or create a new one; recent workspaces are listed
there too. The app never copies your files elsewhere, never connects to the internet and writes
no logs outside `results/`.

## Screens

| Screen | Experiment kinds |
|---|---|
| Portfolios | describe a portfolio in two tables, then create its report config |
| Portfolio report | `portfolio_report` |
| Risk | `risk_report` |
| Scenarios | `scenario_analysis` |
| Projections | `projection` |
| Optimiser | `optimisation` |
| Backtests & studies | `backtest` and the four studies |
| Data | the raw store: source, dataset, download date, age, size, hash and terms of each file; *Import a downloaded file* |
| History | every run, newest first, with status, configurations tried and errors |
| Settings | language, recent workspaces, version information and the settings file |

Each analysis screen has three columns:

- **Left:** the configs of its kinds, with *New from template* and *Duplicate*.
- **Centre:** a TOML editor with *Save*, *Validate* and *Run*. Validation shows the runner's
  messages unchanged.
- **Right:** the results.
  - Each table carries its sample tag (in-sample, out-of-sample or descriptive).
  - The scalars and figures are shown below the tables.
  - *Open report* and *Open folder* open them in the system's browser and file manager.

## Describing a portfolio (Portfolios)

A portfolio is a folder `portfolios/<name>/` with `transactions.csv`, the native qrlab file,
and `instruments.toml`. No broker export is needed. The screen has two tables:

- **Instruments:** one row per fund, with ISIN, name, type, asset class, currency, the date of
  the facts and, where known, domicile, replication, distribution, TER, benchmark, hedging,
  inception, fund size and source. The facts come from the fund's KID or factsheet.
  `unknown` and `none` mean what they mean in the TOML file.
- **Transactions:** one row per transaction, its kind picked from a list. Only the cells its
  kind uses can be edited; the others are greyed out.
- **Starting position:** for what you hold today without its history. It adds a deposit and
  one transfer in per instrument on a start date. You fill in:
  - the units;
  - the market price on that day, which is what performance starts from;
  - your original cost per unit, which gains and taxes use;
  - the cash.

*Validate and save* reads both tables exactly as the report will
({py:mod}`qrlab.experiments.portfolios`).

- **A problem** names its table, its row and the library's message, and nothing is written.
- **When both tables are valid,** both files are written through the library's writers, with
  the rows sorted by date.

*Create report config* writes a `portfolio_report` config with the portfolio's files and
`transactions_format = "native"`, and opens it on the Portfolio report screen. There you fill
in the price file, its mapping, the checks and the parameters, then Validate and Run.

**Prices and issuer files** (holdings, NAV history) are downloaded by you from the issuer's
website. *Import a downloaded file*, on the Data screen, copies one into the raw store,
unchanged, with its provenance. The app never downloads them itself (see
{doc}`data-sources`).

**A Vanguard fund, step by step.**

1. **Download** the two exports from the fund's page on a Vanguard Europe website:
   - *Download* under *Holdings details*;
   - *Download … prices* under *Prices and distribution*.
2. **Copy the price mappings** `configs/csv_mappings/vanguard_prices_market_eur.toml` (and,
   if you want the NAV, `vanguard_prices_nav_usd.toml`) into your workspace. Replace the
   made-up ISIN with your fund's.
3. **In the report config,** use `vanguard_holdings.toml` as the fund's `holdings_mapping`,
   with `as_of` set to the date in the file's preamble ("As at …"). The price mapping goes in
   `prices_mapping`.

**An iShares fund, step by step** (Italian website; see {doc}`data-sources` about its terms).

1. **Download** two files from the fund's page on ishares.com/it:
   - *Informazioni dettagliate sulle partecipazioni e dati analitici*, the holdings CSV;
   - *Scarica*, next to the fund's name, the fund-data file (`.xls`, really an XML
     spreadsheet, with the NAV history).
2. **Copy `configs/csv_mappings/ishares_nav.toml`** into your workspace. Replace the made-up
   ISIN with your fund's, and the currency with your share class's.
3. **In the report config:**
   - `ishares_holdings_it.toml` is the fund's `holdings_mapping`, with `as_of` set to the date
     on the CSV's first line;
   - the NAV mapping goes in `prices_mapping`.

   A country name the mapping does not list stops the run with its line: add it to the
   mapping's `country_values`.

## Things to know

- **One run at a time, and runs cannot be cancelled.** The window stays responsive and shows
  the elapsed time. Closing the app during a run is refused.
- **Unsaved edits are never lost silently.** Changing config or portfolio, opening another
  workspace, changing language or closing the window first asks *Save / Discard / Cancel*. A
  portfolio that does not validate is not saved: the app stays on it and shows the problem.
- **Re-running a config** replaces its outputs after asking. The trial ledger keeps every run.
- **Language:** English or Italian. Numbers and dates on screen follow it; files on disk never
  change. The runner's own messages and identifiers (kinds, files, tables, columns) stay as
  recorded.
- **Settings** are stored in an INI file, never in the Windows registry:
  `%APPDATA%\qrlab\qrlab-app.ini` on Windows. It holds only the language, the recent workspaces
  and the window size.
- **Shortcuts:** `Ctrl+S` saves the config and `F5` refreshes the screen.

## Self-test

`QuantResearchLab.exe --self-test WORKSPACE` (or `qrlab-app --self-test WORKSPACE`) runs every
config of a workspace through the real window, without showing it. It exits with code 0 only if
every run succeeds; a workspace without configs fails. The Windows build uses it in CI, also on
an installed copy.
