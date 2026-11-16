# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0rc1] - 2026-11-16

Release candidate of version 1.0. It was prepared on 2026-11-13 for milestone M6 but not
published; it now also holds Levels 7 to 10. It brings:

- the desktop app, the Windows program and installer, a frozen public API with a
  compatibility policy, the documentation site and the release automation (M6, phases 6.1 to
  6.3c);
- the working paper on the four studies (6.3d);
- the gap closing of Level 7: frequency checks, output notices, the returns price type;
- the report on a portfolio built in the app from public data, with its risk, projection and
  Italian tax position (M8);
- tax regimes for Switzerland and a configured country (M9);
- the local Linux check and the audit before publication (10.1, 10.2).

It is published to TestPyPI to check the release process; 1.0.0 follows with the same code if
nothing is found. The entries for Levels 7 to 10 come first, then those for M6.

### Added

- **The history audit reads the commits and tags too** (phase 10.2): author, committer and
  tagger e-mail addresses, and messages checked like file contents. It still reports hashes
  and paths only, never values.
- **The CI checks, run locally** (phase 10.1): `scripts/ci_local.sh` runs the steps of
  `ci.yml` in order on a fresh clone, on Linux (WSL) or on Windows (Git Bash). A test keeps
  its commands, Python versions and the guide's system libraries equal to the workflow's.
  Guide: *Running the CI checks locally*.
- **iShares files as published** (phase 8.2c), on the owner's decision about the website's
  terms. There are two committed mappings:
  - `ishares_holdings_it.toml`, for the holdings CSV of the Italian website, with Italian
    numbers and country names listed explicitly;
  - `ishares_nav.toml`, for the NAV history of the fund-data file.
- **XML spreadsheets** (SpreadsheetML 2003, which iShares serves as `.xls`) are a third
  `file_format`, `"spreadsheetml"`, for price and holdings mappings
  (`qrlab.data.read_spreadsheetml_rows`). They are read with the standard library, with no
  new dependency. A file with a DOCTYPE or an entity declaration is refused.
- **A configurable tax model for other countries** (phase 9.3), `country = "custom"` in
  `[parameters.tax]`, from `qrlab.tax.custom`.
  - **What you state:**
    - the gains and income rates;
    - losses ignored, or netted and carried N years;
    - an exemption after N months of holding;
    - a yearly gains allowance;
    - a wealth-tax rate;
    - a description.
  - **How it is applied,** per calendar year and in a stated order:
    1. each sale at average cost;
    2. the exempt part, with units matched first in, first out;
    3. losses;
    4. the allowance;
    5. the rates.

    Tax withheld on income is shown, not credited.
  - **Labelled as yours.** The section, its title and the run's notice say "a simplified
    model you configured, not a country's law".
  - **Outputs:** `custom_years.csv`, `custom_losses.csv` (with netted losses), and the
    scalars of the latest complete year.
  - **Projections:** a `custom_tax_model` preset.
- **Shared first-in, first-out lots** (`qrlab.tax.lots`), now used by Switzerland and the
  configurable model. `TaxReport.notice` adds a sentence to the run's notice.
- **Swiss tax analytics of a private investor** (phase 9.2), `country = "ch"` in
  `[parameters.tax]`, which needs `base_currency = "CHF"`. They come from
  `qrlab.tax.switzerland`, with the rules checked on 2026-11-15 against LIFD, LAID, LIP,
  ESTV Circulars 25 and 36 and BGE 151 II 418.
  - **Gains.** Realised gains are tax-free as private wealth. The five ESTV Circular 36
    criteria are checked per year:
    - the holding period, first in, first out;
    - the volume against 5 times the value at the start;
    - the gains against 50 % of the net income you state;
    - debt financing;
    - derivatives.

    The conclusion is "safe haven met", "professional trading not excluded" or "incomplete".
  - **Income:** dividends and interest gross, plus accumulating funds' yearly income from
    the ESTV price-list values you give, with the tax estimated at your marginal rate.
  - **Withholding tax:** the 35 % Swiss withholding tax is shown as refundable.
  - **Wealth:** the year-end wealth, with the tax at your cantonal rate.
  - **Outputs:** `ch_years.csv`, `ch_safe_haven.csv`, `ch_income.csv`, and the scalars of the
    latest complete year.
- **A yearly income tax in projections** (phase 9.2). `TaxModel` gains `income_tax_rate` and
  `taxable_yield`, whose product is paid each year as a fraction of value. The report's
  `[parameters.projection]` takes both keys or neither. `qrlab.tax.swiss_tax_model` is a
  preset with no gains tax.
- **The tax shape** (9.1) gains the `NUMBER` column kind and a per-column `none_label`.
  `TaxRegime` declares the `base_currency` it needs, checked when the config is validated.
- **Tax regimes as a common shape** (phase 9.1), so that countries can be added beside Italy.
  - `qrlab.tax.TaxRegime` is the interface of a country. It reads its own keys of
    `[parameters.tax]` and returns a `qrlab.tax.TaxReport`.
  - The report describes the result: sentences with typed values, tables with typed columns
    (date, year, holding, label, text, money, share), sources in each report language, the
    date the rules were checked, and the run's scalars.
  - The report kind writes the CSV tables and scalars, and the HTML report renders the
    section, from that description alone.
  - `qrlab.tax.REGIMES` lists the countries; Italy is `"it"` (`qrlab.tax.ITALY`,
    `italian_tax_report`). Italian outputs are byte-identical to before.
- **Vanguard files as published** (phase 8.2b), read with three committed mappings:
  `vanguard_holdings.toml`, `vanguard_prices_market_eur.toml` and
  `vanguard_prices_nav_usd.toml`. The mappings follow the exports of a Vanguard Europe fund
  page, read on 2026-11-15.
  - **Price files can be xlsx with a preamble.** `CsvMapping` gains `file_format`, `sheet`
    and `skip_rows`, and `qrlab.data.FileFormat` and `qrlab.data.read_xlsx_rows` are shared
    with the holdings parser.
  - **Symbols next to numbers** (`%`, `$`, `€`) are removed only where a mapping declares
    them, in `value_affixes`; any other character still raises.
  - **Dates may use `%b`,** English month abbreviations read the same on every machine.
  - **iShares:** no mapping. The terms of its Italian website require BlackRock's approval
    for any copy of data. The decision is in `docs/guides/data-sources.md`.
- **A Portfolios screen in the desktop app** (phase 8.8b). It describes a portfolio in two
  tables, transactions and instruments, without a broker export.
  - **Editing.** Each transaction's kind is picked from a list, and only the cells it uses can
    be edited. A *Starting position* helper adds a deposit and one transfer in per instrument.
  - **Validate and save.** It reads the rows as the report will and points at the row with a
    problem. It writes nothing until both tables are valid.
  - **Create report config.** It writes a `portfolio_report` config with the portfolio's files
    and opens it.
  - **Data screen.** *Import a downloaded file* copies a file into the raw store, unchanged,
    with its provenance.
  - **No financial logic in the app.** Everything it calls is in the library:
    - `qrlab.experiments.portfolios`: `read_portfolio`, `check_portfolio`, `write_portfolio`
      and `import_downloaded_file`;
    - `qrlab.instruments`: `INSTRUMENT_FIELDS`, `instrument_from_fields`, `instrument_fields`
      and `write_instruments_toml`;
    - `qrlab.portfolio`: `kind_columns` and `check_transactions`, the replay rules that need
      no rates;
    - `config_template` with `inputs` and `parameters` filled in.
- A native transactions file (phase 8.8a), so that a portfolio can be described without a
  broker export: `qrlab.portfolio.native`, with `NATIVE_COLUMNS`, `NATIVE_MAPPING`,
  `parse_native_csv` and `write_native_csv`.
  - **Layout:** one fixed CSV, with ISO dates, dot decimals and never-negative numbers.
  - **Reading:** it goes through the same validated path as a broker export.
  - **Charges:** fees and taxes are always written with their currency, so none is assumed.
  - **Writing:** the writer sorts by date and keeps ties in order.
- **An original cost on transfers in** (phase 8.8a). `Transaction.cost`, optional and allowed
  only on `transfer_in`, is the cost per unit; brokers and native files map it as
  `cost`/`cost_currency`.
  - **Cost basis.** It becomes the cost basis, so realised gains and the Italian tax use it.
    The external flow stays at market value, so TWR and MWR do not see gains made before the
    transfer.
  - **Gain carried in or out.** Each transfer's gain, market value minus cost basis, is
    recorded (`qrlab.portfolio.TransferGain`, `LedgerHistory.transfers`). The P&L shows it
    apart, as `PnlBreakdown.transfers` and as a report row when it is not zero, so the
    breakdown still reconciles.
- The `portfolio_report` kind reads either format, through the required parameter
  `transactions_format` (`"mapped"` or `"native"`). A declared original cost adds a sentence
  to the run's notice.
- Italian losses in projections and backtests (phase 8.6b). `TaxModel` has an optional
  `losses`, a new `qrlab.simulation.LossRules` (`carry_years`, `fund_assets`):
  - gains on funds are taxed in full and use no losses;
  - every realised loss joins a balance by year;
  - other gains use the losses of the same sale, then the balance, oldest first, for
    `carry_years`.

  Projections keep a balance per path, backtests one by calendar year. Withdrawals still
  pay the stated net amount, solved in closed form. The default, `None`, keeps the old
  behaviour, and for funds only the rules change no number: the examples and the four
  studies are byte-identical. The rules are a library option; the configs do not set them
  yet.
- A report entirely in Italian (phase 8.7). `qrlab.reporting.messages` gives the Italian
  form of every library message a report can show:
  - import notes;
  - why a health check does not apply, including the metric errors it passes on;
  - measurement-detail keys and fixed phrases;
  - the reason a Sharpe ratio is missing.

  Values captured in a message are kept, with the Italian decimal comma.
  - **Only whole messages are translated,** so text you write is never touched.
  - **Guard test.** `tests/unit/reporting/test_messages.py` scans the library's source for
    every message template and detail key, and fails if one has no Italian form. A rendered
    Italian report is also checked for English library phrases.
  - **Tax sources** have an Italian version (`qrlab.tax.italy.SOURCES_IT`).
  - **English reports are unchanged.** Italian reports change only where library text was in
    English, and they drop the "reasons are in English" footnote when every reason is
    translated.
- The Italian tax position of a real account (phase 8.6a), as analytics, not tax advice: the
  new package `qrlab.tax` (`italian_tax_position`).
  - **Categories:** gains on ETFs and funds are *redditi di capitale*; losses on them, and
    results on shares, bonds and ETCs, are *redditi diversi*.
  - **The losses balance (*zainetto*):** losses are kept by year, used oldest first, and
    expire on 31 December of year + 4.
  - **Rates:** 26 %. The share due to government bonds counts for 48.08 %, for bonds and
    funds alike.
  - **Regimes:** amministrato, where each sale is taxed when it happens and compared with the
    tax withheld, and dichiarativo, where the year is netted and the tax is an estimate.
  - **Non-harmonised funds** (domiciled outside the EU and EEA) are flagged, not computed.
  - **Taxable gain:** the ledger's gain is net of the tax withheld on the sale, so the engine
    adds that tax back.
  - **Sources:** the rules carry them and their date (checked 14/11/2026), with the TUIR
    1986 and D.Lgs. 117/2026 article numbers. Sales outside 1/7/2014–31/12/2027 raise.
- **In the `portfolio_report` kind:** an optional `[parameters.tax]` (`regime`,
  `public_share`) adds a "Tax position (analytics, not tax advice)" section, `tax_events.csv`,
  `losses_balance.csv` and the scalars `tax_due`, `tax_withheld` and `losses_remaining`.
  Without it, outputs are byte-identical.
- **Hand-checked:**
  - a five-year sequence with tax due of 572 and 400 of losses expired;
  - the example of Circolare AdE 19/E/2014 (base 258.72, tax 67.27);
  - a government bond (125.01);
  - a bond fund's loss entering the balance at 792.32;
  - dichiarativo netting within a year.
- **Coverage.** Tests close the coverage gaps left by phases 8.2–8.5, mostly validation
  messages and the Cornish-Fisher case. Coverage is back to 100 %.

### Changed

- **The history was rewritten before publication** (phase 10.3). Every commit and tag now
  carries the owner's GitHub `noreply` address, three personal passages in old versions of
  design notes 8.2, 8.6 and 8.7 are replaced by their current wording, and the subjects of the
  66 pull-request merges read `Merge pull request N` without `#`. So every commit hash changed;
  the commit the studies ran on is now `f8ee46c`, with the same files.
- **`risk_report` writes a notice** (phase 10.2): "Risk estimates from past returns under the
  stated model. Future losses can be larger." followed by the not-advice line, in `NOTICE.txt`
  and the record. It was the only kind whose outputs never said they are not advice, because
  it writes no HTML report.
- **Price mappings need `missing_tokens`** (phase 8.2c): cell values that mean "no price",
  besides an empty cell. Add `missing_tokens = []` to an existing price mapping.
- **Holdings mappings may use the same character as delimiter and decimal separator** (phase
  8.2c), because numbers are quoted. An unquoted one changes the field count and is rejected
  per row.
- **`[parameters.tax]` needs `country`** (phase 9.1): add `country = "it"` to an existing
  Italian tax table. A missing or unknown country raises with the list of countries.
- **`build_portfolio_report(tax=...)` takes a `TaxReport`** instead of a `TaxPosition`. Use
  `qrlab.tax.italian_tax_report(position)` to turn an Italian position into one.
- **Price and holdings mappings need new keys** (phase 8.2b):
  - price mappings: `file_format`, `skip_rows` and `value_affixes`, plus `sheet` for xlsx
    (where `delimiter` and `encoding` are then left out);
  - holdings mappings: `value_affixes`.

  Add `file_format = "csv"`, `skip_rows = 0` and `value_affixes = []` to an existing price
  mapping, and `value_affixes = []` to a holdings mapping. A missing key raises with its name.
- **Workspaces have a fourth folder, `portfolios/`** (phase 8.8b). It is created when a
  workspace is opened. The app's *Portfolio* screen is now called *Portfolio report*.
- **`Dialogs` has a new field, `pick_file`** (desktop app).
- **`portfolio_report` configs need `transactions_format`** (phase 8.8a). Add
  `transactions_format = "mapped"` to `[parameters]` of an existing config;
  `transactions_mapping` is now an optional input, refused with `"native"`. A missing key
  raises with this hint.
- **`PnlBreakdown` has a new field, `transfers`,** before `residual`. A transfer out at a market
  value different from its cost basis used to leave that difference in the residual; it now
  appears under `transfers`, and the residual is zero.
- `build_portfolio_report` takes the required keyword `tax` (pass `None` for none).
- A risk-free rate and the Sharpe ratio in the portfolio report (phase 8.5).
  - **`qrlab.core.overnight_returns`** compounds an overnight rate over periods: simple
    interest over weekends and holidays, compounding between business days, as in the ECB's
    compounded €STR averages. `day_count` is explicit (360 or 365). A business day without a
    fixing raises.
  - **The `portfolio_report` kind takes an optional `estr` input** (the ECB €STR file), with
    `return_frequency = "monthly"`. Each monthly TWR period gets the €STR compounded over
    exactly its dates.
  - **In the summary:** the risk-free return and the Sharpe ratio of the excess returns, with
    its Mertens standard error and `n` (e.g. `0.85 ± 0.40 (n = 24)`). If the Sharpe ratio is
    undefined, the report says why.
  - **New outputs:** `risk_free.csv` and the scalars `risk_free_total`, `sharpe_ratio` and
    `sharpe_ratio_se`.
  - **Hand-checked:** a Friday-to-Monday weekend at 3.6 % (0.03 % exactly), the Easter
    five-day fixing, a Sharpe ratio of 4.0249 on (1, 2, 0, 3) %, and the accrual of a whole
    month.
  - **`qrlab.reporting.RiskFreeSummary`** is new. `build_portfolio_report` takes it as the
    required keyword `risk_free` (pass `None` for none): every report input is explicit.
- Projection and savings plan in the `portfolio_report` kind (phase 8.4), with an optional
  `[parameters.projection]`. Without it, outputs are byte-identical.
  - **Starting point:** today's portfolio, its value, weights and date. The kind does not ask
    for them.
  - **Return assumptions:** stated, never estimated from the history. There is one table per
    held position and one for cash. Every pair of risky assets needs a correlation, and none
    defaults.
  - **Plan:** flows (a savings plan), rebalancing, inflation and taxes. Costs are a number or
    `"ter"`, the TER of the instruments file weighted by today's weights.
  - **Seed:** the projection has its own `seed`.
  - **Sensitivity:** always computed, and it cannot be switched off in the report.
  - **Outputs:** the report's projection section, `fan_real.csv`, `terminal.csv`,
    `sensitivity.csv` and the fan chart. The scalars are `projection_p_goal`,
    `projection_p_goal_se`, `projection_terminal_mean_real` and `projection_annual_cost`.
  - **Notice:** "not a forecast", the notice of 7.2.
  - **Hand-checked:**
    - a deterministic plan (zero volatility) ending at 11,856.50 EUR, to the cent;
    - the log-normal median within four Monte Carlo standard errors;
    - a weighted TER of 0.16 %;
    - cash compounding on its own without rebalancing.
  - **Shared code:** the `projection` kind now shares its plan code with the report
    (`run_plan`, `parse_engine`, `parse_flows`). Its outputs are byte-identical.
- Risk and stress tests in the `portfolio_report` kind (phase 8.3), with an optional
  `[parameters.risk]`: `frequency` (`weekly`/`monthly`), `window`, `confidence`, `covariance`.
  There is also an optional `scenarios` input. Without them, outputs are byte-identical.
  - **Returns:**
    - built from the report's own price files, including dates before the first purchase;
    - the last price per period, converted with the ECB rates of `fx`;
    - foreign cash returns its currency's return;
    - nothing is filled, and a position that lacks the window fails the run and is named.
  - **Weights:** today's, applied to past returns: what this portfolio would have done, not
    the TWR.
  - **What is computed:** volatility contributions, VaR and ES (historical, normal,
    Cornish-Fisher) and stress tests, in the report's risk section.
  - **Undefined methods:** a method that is undefined, such as historical VaR on too few
    returns, is listed with its reason instead of being forced.
  - **New outputs:** `risk_returns.csv`, `risk_contributions.csv`, `var_es.csv` and
    `scenarios.csv`, plus the scalars `volatility_period`, `volatility_annual` and the
    historical VaR and ES.
  - **Notice:** when the prices are price-only, it says that return levels exclude dividends.
  - **Hand-checked:** a 0.70711 % monthly volatility with contributions of 0.58926 % and
    0.11785 %; a USD fund at +25 % in EUR (+10 % in USD); USD cash at +13.64 %; a −30 % shock
    on a fund at 50 % giving −15 %.
- Issuer holdings files as published (phase 8.2a: the reading layer; the iShares and Vanguard
  mapping files follow in 8.2b, from the real downloads).
  - **Country names.** `qrlab.instruments.countries` maps one ISO 3166-1 short name per code,
    plus listed aliases ("Korea (South)", "Taiwan", "Turkey"…), to alpha-2 codes. Matching
    ignores case, accents and spacing. An unknown name raises with its line; it is never
    guessed. The names were checked against `pycountry` 26.2.16, which is not a dependency.
  - **Holdings mappings** gain three keys:
    - `country_format`: `"iso_alpha2"` or `"name"`;
    - `country_values`: the file's own wording mapped to a code or `"unknown"`, such as
      "European Union" or a cash line;
    - `file_format`: `"csv"` or `"xlsx"`, with `sheet` for a workbook.
  - **`parse_holdings_file`** reads CSV and xlsx files alike. Numeric cells are read as numbers.
  - **Overlap matched by name.** Where a fund lists a security without an ISIN, the overlap
    between funds also matches by normalised name (`qrlab.lookthrough.names.name_key`). This
    part is reported on its own (`Overlap.by_name`) and labelled approximate in the report.
    Two ISINs are never matched by name, and cash lines never are.
  - **Issuer maps.** `load_issuer_map` reads a CSV `isin,issuer`; the `portfolio_report` kind
    takes it as an optional `issuers` input, with holdings files. Example: two share classes of
    one company count as one issuer.
- New runtime dependency **openpyxl** (MIT). Reason: Vanguard publishes holdings as Excel
  workbooks. Converting them to CSV by hand would be an unrecorded transformation of a raw
  file, and it can change numbers and dates. It is used only to read xlsx holdings. New dev
  dependency `types-openpyxl`, for mypy.

### Changed

- **Breaking against the M6 code** (never published), **for holdings mappings:**
  `country_format` and `file_format` are now required, with `delimiter` and `encoding` for CSV
  and `sheet` for xlsx. Add `file_format = "csv"` and `country_format = "iso_alpha2"` to keep
  the old behaviour. 1.0.0 is not released yet.
- The report's overlap table has a new column, "Of which by name", and a note.
- Look-through and tracking in the `portfolio_report` kind (phase 7.4b), all optional. Without
  them, the existing configs run with byte-identical outputs.
  - **Holdings:** the groups `holdings` and `holdings_mapping`, keyed by fund ISIN, with
    `[parameters.holdings.<ISIN>]` (`as_of`, `weight_basis`, `sector_taxonomy`).
    `lookthrough_treatment` is required with holdings and refused without them.
  - **Tracking:** the groups `tracking` and `tracking_mapping`, two-column price files with the
    fund's NAV or total return and its index's total return, with
    `[parameters.tracking.<ISIN>] index_hedged_to`.
  - **What it feeds:** the look-through on the last valuation date goes to the report's
    look-through section and to the nine look-through, tracking and stale-holdings checks.
  - **New outputs:** `exposures.csv` and the scalars `lookthrough_funds` and
    `unexplained_weight`.
  - **What is refused:** holdings or tracking for a fund not held, and holdings dated after the
    report.
  - **Hand-checked:** 24.0 / 15.0 / 12.0 / 8.4 % and 0.6 % unexplained for a fund at 60 %, and a
    tracking difference of -0.09 %. The kind's exposures equal `look_through` called directly.
  - **Full example:** `example_portfolio_report_full.toml` now includes look-through and
    tracking, and the app's smoke test runs it. Its USD fund now has its own made-up ISIN,
    `US0000001000`, distinct from a security in the world fund's holdings.
- Several currencies in the `portfolio_report` kind (phase 7.4a). All of it is optional:
  existing configs run unchanged, with byte-identical outputs.
  - **`fx` input:** the ECB `eurofxref-hist` zip. Its provenance comes from the raw store's
    sidecar, checked against the file's SHA-256. With it, amounts and prices are converted with
    the reference rate of their date, through EUR for a non-EUR base. The report lists every
    rate carried forward.
  - **`fx_max_age_days`:** required with `fx` and refused without it.
  - **`[inputs.extra_prices]` and `[inputs.extra_prices_mapping]`:** one more price file per
    currency, under the same key. An ISIN in two price files raises.
  - **New example:** `configs/experiments/example_portfolio_report_full.toml`, with a USD fund,
    USD cash and synthetic rates in the ECB format. A test checks it against a hand calculation
    (15,482 EUR).
- Groups of input files in experiment configs (phase 7.4a). An input may be a table of files
  with free keys, e.g. `[inputs.extra_prices]`. Each file is flattened to `<group>.<key>` and
  hashed and recorded like any other input.
  - **New `ExperimentKind` fields:** `input_groups`, `optional_parameters`, and
    `check_inputs`, a validation hook for rules that tie parameters to the inputs given.
  - **New method:** `RunContext.group`.
  - **Where they show:** `qrlab kinds` and the config templates list the groups and the
    optional parameters.
- Notices that travel with the outputs (phase 7.2). The `projection`, `optimisation`,
  `scenario_analysis` and `backtest` kinds now state what their outputs are not: a forecast, a
  recommendation or a probability of loss. Each notice ends with "Research analytics, not
  investment advice."
  - **Where it appears:** `NOTICE.txt` in the output folder (tagged `descriptive`), a new
    `"notice"` field in `record.json` (`null` for the other kinds), the `qrlab run` output and
    the app's results panel. `RECORD_FORMAT` stays 1: the field is an addition.
  - **In the figure:** the projection fan chart carries a footer, "Scenarios from stated
    assumptions, not a forecast.", through the new `line_figure(note=...)` parameter. Without a
    note, figures are byte-identical to before.
  - **Sensitivity off:** a projection run with `sensitivity = false` says so in its notice.
  - `ExperimentOutput` gains `notice: str | None = None`.
- `qrlab.core.require_periods_per_year` (phase 7.1): a `periods_per_year` that contradicts the
  dates' frequency now raises, with the value to use. For example, 252 on monthly data raises
  with "use 12".
  - **Where it applies:** every annualising metric, `factor_exposures`, the tracking error,
    `summarize_backtest`, and the `risk_report` and `optimisation` kinds.
  - **When it does not:** series whose dates have no recognisable frequency are not checked.

### Changed

- **Breaking against the M6 code** (never published), **for configs:** the returns files of
  four kinds must declare whether they include dividends (phase 7.3).
  - **The new required key:** `returns_price_type` in `backtest`, `optimisation` and
    `risk_report`, and `position_returns_price_type` in `scenario_analysis`. A config without
    it fails validation and names the key.
  - **Values:** `"total_return"` or `"price"`. `"nav"` is refused, because a NAV return
    includes the income of an accumulating fund but not of a distributing one; the message
    says which to declare.
  - **What it does:** the declaration changes no number. With `"price"`, the run's notice says
    that return levels are understated by about the dividend yield. `risk_report` has a notice
    only in that case.
  - **Why required:** a default would be the silent assumption this removes. 1.0.0 is not
    released, so it is not a 2.0 change. The example configs declare `"total_return"`.

### Fixed

- The beta health check passed `periods_per_year=1` whatever the frequency of the returns. Its
  result was unaffected, because only the unused alpha is scaled; it now passes the value that
  matches the dates (regression test).

### Added

- The working paper (phase 6.3d), *What survives? Four reproducible studies of portfolio rules
  under real-time implementation, costs and multiple testing*, in `docs/paper/` and on the
  documentation site.
  - **Numbers come from the records.** `scripts/paper_values.py` generates every number and
    table from the study records, as declared in `docs/paper/values/*.toml`; the text uses MyST
    substitutions only.
  - **Checks.** `--check` regenerates from the records and fails on any difference, and a test
    requires every generated value to be used and every substitution to be defined.
  - **Reproducibility appendix.** Run dates, versions, commits, seeds, configurations tried and
    the exact data files with their hashes.

### Changed

- The four studies were re-run from a clean checkout of commit f8ee46c, with the same data
  files and trial ledgers: all nine runs gave byte-identical outputs. The paper's reproducibility
  appendix now cites these records, and the reports note the re-run.

### Fixed

- Last-digit figures in the study reports, found while generating the paper from the records:
  - **Study 1:** RMW z 1.46, Holm 0.71, mean weight 0.77; CMA z −0.66; momentum at 2× and
    25 bp 0.78.
  - **Study 2:** the HRP CEQ gap is 0.6–0.9 % a year. Sample maximum Sharpe on D1 is below 1/N
    everywhere, but BL maximum Sharpe is as low, so it is not "the lowest".
  - **Study 3:** 87 % of clear predictors are positive after publication, not 86 %.
  - **Study 4:** five shares that end in exactly 5 are now rounded half-up, as everywhere else.

### Changed

- The Windows build no longer runs on every push to `main`, nor on PRs that change only
  `pyproject.toml`. It still runs for every release, on PRs that change the packaging, its
  workflow or `uv.lock`, and by hand. This saves Actions minutes: a run takes 6-7 minutes on
  Windows runners.

### Added

- Release preparation (phase 6.3c):
  - **Licence:** the BSD-3-Clause `LICENSE`; documentation and study reports under CC BY 4.0.
  - **Citation:** `CITATION.cff` and `.zenodo.json`.
  - **Community files:** `CONTRIBUTING.md` and `SECURITY.md`.
  - **Release workflow:** on a version tag, `release.yml` checks the tag against the version,
    builds and tests the sdist, the wheel and the Windows program, drafts a GitHub Release, and
    publishes to TestPyPI (release candidates) or PyPI by trusted publishing, after the owner's
    approval.
  - **Docs deployment:** `docs-pages.yml` publishes the documentation to GitHub Pages on final
    tags.
  - **Release guide:** `docs/project/releasing.md`.
- `scripts/audit_history.py`: scans every file version in the git history for private data
  files, spreadsheets, secrets, IBANs, e-mail addresses and the ISINs of the real portfolio
  (read locally from a git-ignored folder). It reports paths and counts only.
- `scripts/readme_figures.py`: the README figures, drawn from the study records.

- Documentation site (phase 6.3b), built with Sphinx, MyST-Parser and pydata-sphinx-theme:
  - getting started, and guides to experiments, the experiment kinds, the desktop app,
    reproducing the studies and the data sources;
  - one methodology page per risk in the risk register, each with its limits; the register in
    `ARCHITECTURE.md` is corrected where it promised more than the code does;
  - the four studies;
  - the API reference generated from the docstrings;
  - the changelog, the architecture, the roadmap and the design notes.

  A new `docs` job in CI builds it with warnings as errors and runs the guides' examples as
  doctests, without network access.
- `qrlab.data` now exports the Open Source Asset Pricing functions used by study 3:
  `download_osap`, `parse_long_short_returns`, `parse_signal_doc`, `OSAP_FILES` and
  `OSAP_REVISION`.
- New dependency group `docs` (Sphinx, myst-parser, pydata-sphinx-theme). Reason: the
  documentation tool chosen in design note 6.3 (D3); not a runtime dependency.

- The public API is frozen for 1.0 (phase 6.3a):
  - `docs/api/public-api.txt` lists every public name with its signature, and
    `tests/unit/test_public_api.py` fails on any change that is not reflected there;
  - `docs/compatibility.md` states the Semantic Versioning promise, what is and is not public,
    and the deprecation rule.
- `qrlab.experiments.RECORD_FORMAT`: every `record.json` now has `"format": 1`.

- Windows build (phase 6.2), in `packaging/`, built by the new workflow
  `.github/workflows/app-build.yml`:
  - **Contents:** a PyInstaller one-folder build holding `QuantResearchLab.exe` (the app) and
    `qrlab.exe` (the command line), with `build-info.json`, `THIRD_PARTY_NOTICES.txt` and the
    LGPL/GPL texts.
  - **Deliverables:** a per-user Inno Setup installer that needs no administrator rights and
    never touches workspaces or settings, a portable zip, and `SHA256SUMS.txt`, uploaded as
    workflow artifacts.
  - **CI checks:** the six examples run from source and from the frozen `qrlab.exe` must give
    byte-identical outputs. The frozen app's self-test must pass, both from the build folder
    and after a silent install. Uninstalling must remove the program and keep the workspace.
- `QuantResearchLab.exe --self-test WORKSPACE` (`qrlab_app.selftest`): runs every config of a
  workspace through the real window, without showing it. It exits with 0 only if all runs
  succeed; an empty workspace fails.
- New dependency group `build` (`pyinstaller` 6.22). Reason: the roadmap's packaging tool. It
  is GPL-2.0 with the bootloader exception, and it is not a runtime dependency.

- The app in Italian and English (phase 6.1c):
  - every app string, error message, sample tag and run status is in both languages;
  - numbers and dates on screen follow the language (`0,0317`, `1.234.570`, `12/11/2026`);
    missing values show as `—`, and the files on disk never change;
  - the runner's messages and all identifiers (kinds, files, tables, columns, scalars) stay as
    recorded.
- The app's Settings screen: language (applied at once by rebuilding the window, never during a
  run), recent workspaces, version information and where the settings file is. Settings live in
  an INI file (`%APPDATA%/qrlab/qrlab-app.ini` on Windows), not in the registry.
- Recent workspaces on the Home screen (at most 8; missing folders are marked and cannot be
  opened). The window title shows the open workspace, and the window size is remembered.
- `reporting.formatting.format_significant`: significant figures with the language's
  separators, half-up on the decimal value, scientific notation outside `[1e-4, 1e12)`.

- Experiment kinds for the app's Risk, Scenarios and Optimiser screens (phase 6.1b), thin
  adapters over tested library functions, each with a synthetic example config:
  - `risk_report`: covariance (sample, EWMA, Ledoit-Wolf), contributions to volatility and to
    historical and normal ES, VaR/ES by four methods (Cornish-Fisher left empty with its
    reason when not a quantile), and a VaR backtest with Kupiec and Christoffersen tests;
  - `scenario_analysis`: phase 3.2 stress tests from a holdings CSV, with optional position
    returns, factors, betas and FX;
  - `optimisation`: 1/N, minimum variance, mean-variance, maximum Sharpe, risk parity,
    maximum diversification and HRP, in sample, with bounds.
- Optional inputs for experiment kinds (`ExperimentKind.optional_inputs`); the CLI and config
  templates list them.
- The app's Risk, Scenarios and Optimiser screens.
- Desktop app `qrlab_app` (phase 6.1a, PySide6), started with `qrlab-app`:
  - Home (open or create a workspace), Portfolio, Projections, Backtests & studies, Data and
    History screens;
  - a TOML editor with Validate and Run;
  - runs in a worker thread, one at a time, with confirmation before outputs are replaced;
  - results with their sample tags, scalars and figures;
  - the report and folder open in the system browser.

  There is no financial logic in the app: a test enforces that it imports only
  `qrlab.experiments` and `qrlab.reporting`. Qt-free view-models are unit-tested; an off-screen
  smoke test runs an experiment end to end.
- `experiments.workspace`: `create_workspace`, `list_configs` (with validation status),
  `list_runs`, `list_raw_files` (provenance and age) and `config_template`.
- Optional extra `app` (`PySide6-Essentials`, also in the dev group). Reason: the roadmap's GUI
  toolkit; "Essentials" avoids the large add-ons such as QtWebEngine.

### Changed

- The README is rewritten for the public release: status, features, the four studies with two
  figures, install, quality, data and privacy, citation and licence. Its links are absolute,
  so they also work on PyPI.
- `pyproject.toml` declares the licence (PEP 639), keywords, classifiers and project URLs, and
  no longer blocks uploads.
- The Windows build is reusable (`workflow_call`): release tags now build it through
  `release.yml`.
- **Breaking:** `qrlab.stats.FactorModel` is renamed to `qrlab.stats.FactorSet`, so it is no
  longer confused with the factor risk model `qrlab.risk.FactorModel`. It is the only rename
  from the review of the 341 public names before the API freeze.
- Run records gain `code.frozen`. In a frozen program the commit comes from the bundled
  `build-info.json`, with the build time in `code.built`, and `git` is never started. A missing
  or incomplete file refuses the run before anything is written.
- CI installs the Qt system libraries on Linux for the off-screen app tests.
- The app no longer loses unsaved edits: changing config, creating or duplicating one, opening
  another workspace, changing language or closing the window first asks *Save / Discard /
  Cancel*. Closing the window during a run is refused, because runs cannot be cancelled.
- App editor: monospace font without line wrapping; `Ctrl+S` saves and `F5` refreshes the
  screen.

## [0.4.0] - 2026-11-12

Milestone M5 (Research): phases 5.1 to 5.3. There are four reproducible studies with written
reports in `docs/studies/`, each run on real data through the experiment runner:

- volatility-managed factors;
- 1/N against optimised portfolios;
- the factor zoo;
- rebalancing for a EUR ETF investor.

### Added

- Study 4 report, `docs/studies/04-rebalancing.md`, and its two configs in `configs/studies/`
  (60/40 and 80/20), run on Ken French and ECB data of 2026-11-12, October 2004 to September
  2026:
  - monthly rebalancing ends with about €14k less after tax than annual over 20 years (worse in
    99.9 % of paths);
  - buy-and-hold ends richer in 84 % of paths, but drifts to about 86 % equity with more
    volatility and deeper drawdowns;
  - a 5-point band trades far less than quarterly but tracks the target like annual
    rebalancing, so H1 is not supported.
- Study 4 (phase 5.3), rebalancing rules for a EUR ETF investor after costs, Italian tax and
  currency:
  - `qrlab.studies.rebalancing`:
    - world equity converted to EUR at ECB month-end rates;
    - a rolled 7-year AAA zero-coupon bond built from continuously compounded ECB spot rates;
    - seven policies (buy-and-hold, three calendars, three bands) run through the backtest
      engine;
    - after-tax wealth with liquidation tax, and path metrics;
    - stationary-bootstrap paths shared by all policies, paired comparisons and hypothesis
      shares;
    - an HTML report;
  - experiment kind `study_rebalancing`, tested end to end on synthetic files.
- `data.ecb`: AAA euro-area spot rates at 6 and 7 years (`yc_aaa_spot_6y`, `yc_aaa_spot_7y`)
  and `parse_yield_curve`.
- `backtest.BacktestResult.final_basis`: net-ledger cost basis per asset at the end.

- Study 3 report, `docs/studies/03-factor-zoo.md`, and its two configs in `configs/studies/`
  ("clear" and "clear and likely" predictors), run on OSAP release 2026.10:
  - in their original samples, 92.5 % of "clear" predictors pass a single test, 63 % pass
    t > 3 and 52 % pass Holm;
  - returns are 35 % lower after the sample and 58 % lower after publication;
  - the post-publication composite is still positive (0.68 % per month, t = 6.0).
- `studies.factor_zoo.gap_shares`; the factor-zoo kind excludes and lists predictors with more
  than 1 % missing months (approved deviation).
- Study 3 (phase 5.3), the factor zoo (Harvey, Liu and Zhu 2016; McLean and Pontiff 2016) on
  Open Source Asset Pricing data:
  - `qrlab.studies.factor_zoo`:
    - phases of each predictor (original sample, post-sample, post-publication);
    - per-predictor Newey-West tests and counts under single-test, t > 3, Holm, BH and BY
      rules;
    - the McLean-Pontiff decay regression;
    - equal-weighted composites by phase;
    - an HTML report;
  - experiment kind `study_factor_zoo`, tested end to end on synthetic files.
- `data.open_asset_pricing`: pinned downloads into the raw store and strict parsers for the
  predictor long-short returns (Parquet) and `SignalDoc.csv`. The terms (CC BY 4.0) are
  recorded in the data-source table.
- `stats.panel`: fixed-effects OLS with cluster-robust errors and linear contrasts,
  cross-checked against statsmodels with dummies.
- Optional extra `parquet` (`pyarrow`), also in the dev group. Reason: OSAP publishes returns
  only as Parquet.

- Study 2 report, `docs/studies/02-one-over-n.md`, and its two configs in `configs/studies/`
  (main run and paper period), run on the Ken French data of 2026-11-12:
  - no optimised strategy has a significantly higher net Sharpe ratio than 1/N after Holm
    (H1 supported);
  - shrinkage and Black-Litterman do not significantly improve on sample estimates (H2 not
    supported).
- `data.ken_french.AVERAGE_MARKET_CAP`: the 25 size/BM file names its size section
  "Average Market Cap".

- Study 2 (phase 5.3), 1/N against optimised portfolios (DeMiguel, Garlappi and Uppal 2009),
  extended with Ledoit-Wolf shrinkage, risk parity, HRP and Black-Litterman:
  - `qrlab.studies.one_over_n`:
    - rolling-window targets for eight long-only strategies;
    - execution through the backtest engine on daily returns, one trading day after each
      month-end decision;
    - net excess returns, Sharpe ratio, CEQ, turnover and drawdown;
    - Ledoit-Wolf HAC and Jobson-Korkie-Memmel tests against 1/N, with bootstrap intervals of
      the Sharpe and CEQ differences;
    - Holm and BH corrections, the deflated Sharpe ratio and an HTML report;
  - experiment kind `study_one_over_n` (tested end to end on synthetic files).
- `optimization.maximum_sharpe`: the long-only maximum Sharpe ratio (Cornuejols-Tutuncu change
  of variables).
- `data.ken_french`:
  - the 10 industry and 25 size and book-to-market portfolio files, daily and monthly;
  - sections selected by their exact title;
  - `parse_ken_french_table` for the number of firms and the average firm size.
- Study 1 report, `docs/studies/01-volatility-managed.md`, and its three configs in
  `configs/studies/` (main run, paper sample, demeaned variance), run on the Ken French data of
  2026-11-12:
  - in sample, Mkt-RF, RMW and Mom have significant positive alphas after Holm;
  - in real time and after costs, only momentum with a 2x or 5x leverage cap has a
    significantly higher net Sharpe ratio;
  - SMB and CMA become significantly worse at 25 bp.
- `qrlab.studies` (phase 5.3) with study 1, volatility-managed factors (Moreira and Muir 2017
  against Cederburg et al. 2020):
  - monthly realised variance from daily returns, the lagged inverse-variance signal (shifted
    by calendar months), full-sample and real-time scales, leverage caps and turnover costs;
  - the in-sample spanning regression with Newey-West errors and the real-time comparison of
    net Sharpe ratios (Ledoit-Wolf HAC test, stationary-bootstrap interval);
  - Holm and Benjamini-Hochberg corrections across factors, and the deflated Sharpe ratio of
    the best variant with the number of trials taken from the trial ledger;
  - an HTML report that keeps in-sample and out-of-sample results apart.
- Experiment kind `study_volatility_managed`, which runs study 1 on the six Ken French factor
  files (tested end to end on synthetic files), and `experiments.configurations_tried`.
- `qrlab.experiments` and the `qrlab` CLI (phase 5.2):
  - TOML experiment configs, with strict keys and hashed inputs;
  - a `record.json` per run (config, inputs, outputs with sample tags, code version,
    status);
  - a trial ledger that counts the distinct configurations tried;
  - the commands `qrlab run`, `validate` and `kinds`.
- Experiment kinds `portfolio_report`, `backtest` and `projection`, with example configs in
  `configs/experiments/` and synthetic inputs in `examples/data/`.
- `stats.multiple_testing` (phase 5.1): Holm, Benjamini-Hochberg and Benjamini-Yekutieli
  corrections, cross-checked against statsmodels.
- `metrics.sharpe_inference` (phase 5.1):
  - probabilistic and deflated Sharpe ratios;
  - Jobson-Korkie-Memmel and Ledoit-Wolf HAC tests of Sharpe-ratio differences;
  - a stationary-bootstrap interval for the difference.

### Fixed

- `data.open_asset_pricing.parse_signal_doc` refused the real release 2026.10: it has a "Drop"
  category, "indirect" predictability and missing signs for non-predictors. Only predictors
  are strict now. Regression test added.
- `optimization.maximum_sharpe` accepted only a solver success. SLSQP can stop at the optimum
  with a line-search status: this happened in 2 of about 4,000 real Black-Litterman inputs.
  The function now also accepts a feasible point that meets the KKT conditions of the convex
  problem, which makes it the global optimum. Regression tests added.
- The 25 size/BM portfolio file was read with the wrong size-section title; the strict parser
  refused it, and no data was misread. Regression test added.

## [0.3.0] - 2026-11-12

Milestones M3 (Risk & Planning) and M4 (Construction & Backtest): phases 3.1 to 4.4.

### Added

- `qrlab.risk` (phase 3.1):
  - covariance estimators: sample, EWMA (explicit decay and demeaning) and Ledoit-Wolf
    shrinkage, each checked to be positive semi-definite;
  - risk contributions to volatility, historical ES and normal ES, which sum to the totals;
  - Meucci's effective number of bets;
  - a factor risk model with factor and specific contributions;
  - Cornish-Fisher VaR and ES (refused when the expansion is not a quantile);
  - filtered historical simulation with an EWMA filter;
  - VaR forecasts that use only earlier data, with Kupiec and Christoffersen backtests.
- Check `diversification.effective_bets` (37 checks in total).
- `qrlab.scenarios` (phase 3.2):
  - historical replays: direct from a position's own history, by factor proxy compounded
    period by period, or reported as not covered;
  - an explicit currency effect;
  - hypothetical shocks to factors, positions and currencies;
  - scenario files in TOML (`configs/scenarios/example.toml`, example definitions).
- `qrlab.attribution` (phase 4.4):
  - Brinson-Fachler by segment (allocation, selection, interaction), linked over periods
    with Carino or reported with its residual;
  - factor attribution, with alpha and its standard error;
  - one-period currency attribution (local, currency, cross).
  - Every method adds up exactly to the active return.
- `examples/attribution_example.py`.
- `qrlab.backtest` (phase 4.3):
  - strategies see only the history up to their decision date, and an execution lag of
    at least 1 is required;
  - precomputed targets use the same lag;
  - weights drift between trades, and the 4.2 policies (or `TradeOnSignal`) decide the
    trades;
  - costs and capital-gains tax hit the net ledger, with the gross ledger alongside;
  - `summarize_backtest` reports gross and net statistics side by side.
- `examples/backtest_strategies.py`: trend and momentum strategies on synthetic data, gross
  against net.
- `qrlab.optimization` (phase 4.2):
  - explicit constraints (long-only, bounds, groups, turnover), with a feasibility check
    and a post-solve check of every constraint;
  - methods: 1/N, minimum variance, mean-variance and the efficient frontier, risk
    budgeting and ERC, maximum diversification, hierarchical risk parity, and
    Black-Litterman;
  - calendar and threshold rebalancing policies, and trade costs.
- `examples/portfolio_construction.py`: methods compared out of sample on walk-forward
  splits.
- `qrlab.validation` (phase 4.1): walk-forward splits, expanding and rolling, with
  purging of overlapping labels and an embargo. Every split checks that each training label
  ends before the first test time. A property test covers 500 random configurations.
- `qrlab.simulation` (phase 3.3):
  - Monte Carlo engines: normal and Student-t on log returns, and a block bootstrap of
    history; an explicit Generator and cell limit are required;
  - plans with contributions and net withdrawals (fixed or indexed), explicit timing,
    costs, inflation, capital-gains and wealth taxes on an average cost basis, rebalancing
    and depletion;
  - outcomes: fan charts, terminal percentiles (real, nominal, after tax), goal and
    depletion probabilities with Monte Carlo errors, sequence-of-returns risk, and a
    sensitivity table on common random numbers.
- Report section "Projection" with a fan chart, and `examples/projection_plan.py`.
- Report section "Risk and stress tests": volatility contributions, VaR and ES by method,
  and scenario results with coverage and the dates used (`RiskSummary`).
- `examples/risk_models.py`, with an integration test.
- Dev dependency `scikit-learn`, used only in tests to cross-check Ledoit-Wolf.

### Changed

- Layering: `risk` may import `core`, `stats` and `metrics`; `checks` and `reporting` may
  import `risk`. `scenarios` may import `core`, `data`, `instruments`, `metrics`, `risk`
  and `portfolio`; `reporting` may import `scenarios`.
- `build_portfolio_report` requires a `risk` argument (a `RiskSummary` or `None`) and a
  `projection` argument (a `ProjectionResult` or `None`).
- Layering: `simulation` may import `core`, `stats` and `metrics`; `reporting` may import
  `simulation`. `optimization` may import `core`, `stats`, `metrics` and `risk`.
  `backtest` may also import `optimization` and `simulation`. `attribution` may import
  `core`, `stats` and `metrics`.

## [0.2.0] - 2026-11-11

Milestones M1 (Analytics core) and M2 (Portfolio X-ray): phases 1.1 to 2.5.

### Added

- `qrlab.core` (phase 1.1):
  - `errors`: exception hierarchy (`QrlabError`, `ValidationError`, `AlignmentError`,
    `CurrencyError`, `CurrencyMismatchError`).
  - `series`: validation of time-indexed series and frames with an explicit `NanPolicy`;
    unsorted or duplicated indexes raise; `require_same_index` refuses silent alignment.
  - `calendar`: `Frequency`, a reference table of conventional periods per year (never a
    default), diagnostic `infer_frequency`, Gregorian Easter and the TARGET2 calendar.
  - `returns`: `ReturnKind`, prices to returns, simple/log conversion, excess returns,
    compounding, wealth index and aggregation with required `min_periods` and per-bucket counts.
  - `money`: `Currency`, exact `Decimal`-based `Money`, dated `FxRate` and explicit `convert`.
- `qrlab.data` (phase 1.2):
  - `store`, `provenance`, `fetch`: append-only raw store with SHA-256-verified vintages and
    JSON provenance; HTTPS-only fetcher; `Dataset` with unit, frequency, currency and
    point-in-time availability.
  - `ken_french`: FF3, FF5 and momentum factors (monthly, annual, daily), strict parser.
  - `ecb`: euro reference FX rates (with a no-forward-fill bridge to `FxRate`), €STR and
    euro-area HICP from the ECB Data Portal.
  - `user_csv`: user price files read through explicit TOML mappings
    (`configs/csv_mappings/example_prices.toml`).
- `qrlab.instruments` (phase 1.3):
  - `identifiers`: `Isin` with ISO 6166 check digits; ISO 3166-1 alpha-2 country codes.
  - `master`: `Instrument` master data (TER as a bounded fraction, fund-only fields) and
    `master_data_issues` for missing, stale, future and duplicated records.
  - `holdings`: `HoldingsSnapshot`, `holdings_issues` (weight gaps, duplicates, unknown shares,
    staleness) and the explicit `normalised_weights`.
  - `io`: TOML master data and issuer holdings CSVs through a declared mapping
    (`configs/instruments/example.toml`, `configs/csv_mappings/example_holdings.toml`).
- `qrlab.metrics` (phase 1.4):
  - `performance`: arithmetic and geometric annualised return, volatility, Sharpe ratio with
    Lo (2002) or Mertens (2002) standard errors, Sortino, downside deviation, hit rate,
    gain/loss ratio.
  - `drawdown`: drawdown series and episodes from initial wealth, maximum drawdown, Ulcer
    index, Calmar ratio.
  - `moments`: bias-corrected skewness and excess kurtosis.
  - `risk`: historical (Acerbi-Tasche ES) and normal VaR and ES, as positive one-period losses.
  - `relative`: tracking error, information ratio, CAPM regression with OLS standard errors,
    up/down capture, active share.
  - `UndefinedMetricError` instead of silent NaN or infinity.
- `qrlab.portfolio` (phase 2.1):
  - `transactions` and `ledger`: validated transactions per kind; replay into positions and
    cash per account and currency with average cost including charges (Italian "costo medio
    ponderato"); realised gains, income, costs (including FX conversion spreads), external
    flows; impossible states raise.
  - `valuation`: valuation in the base currency with explicit staleness limits for prices
    and ECB FX rates (`EcbConverter`); total-return prices refused.
  - `performance`: TWR with explicit flow timing, MWR (XIRR) with every root reported, exact
    P&L decomposition with the cash FX effect, money contribution by position, currency
    effect.
  - `broker_import`: broker exports through explicit TOML mappings
    (`configs/csv_mappings/example_broker.toml`).
- `qrlab.reporting` v1 (phase 2.3): Italian/English formatting and labels, tables,
  deterministic PNG figures, self-contained HTML rendering, and `build_portfolio_report`
  (summary with TWR and MWR kept apart, positions, cash, P&L breakdown, income and costs,
  charts, data sources and assumptions, visible warnings, "not investment advice").
- `examples/portfolio_report.py` (writes to the git-ignored `results/`), with health checks.
- `qrlab.checks` (phase 2.4): a health-check engine and 27 checks:
  - checks by category: concentration, diversification, risk, costs, ETF quality,
    currency, drift and data quality;
  - each check has a fixed direction, configurable warning and critical thresholds with
    strict comparisons, and findings that carry the numbers;
  - a missing input makes a check not applicable, with the reason; it never passes;
  - the config must list every check (`configs/checks/example.toml`, example values,
    not recommendations).
- `instruments.Instrument.fund_size` (TOML key required, `"unknown"` allowed) and
  `portfolio.TradeCharge` / `LedgerHistory.trade_charges` for the cost checks.
- `qrlab.lookthrough` (phase 2.5):
  - exposures through fund holdings by country, sector, currency (after hedging and
    underlying), security and issuer;
  - explicit buckets for unknown values, weight the holdings do not explain, funds without
    holdings, and cash;
  - pairwise fund overlap and duplicated exposure;
  - tracking difference (annualised only over a year or more, complete calendar years),
    tracking error, and TD + TER;
  - `LookThroughInputs` for checks and reports.
- Nine checks through holdings and tracking series (36 in total): country, sector and
  issuer concentration, fund overlap, duplicated exposure, tracking difference, tracking
  error, costs beyond the TER, stale holdings.
- Report section "Look-through" with holdings dates, exposures, overlap and tracking.
- Report section "Health checks" / "Controlli di salute", with names and explanations of
  every check in Italian and English (`reporting.check_labels`).
- `qrlab.stats` (phase 2.2): `ols` with classical, White and Newey-West standard errors
  (statsmodels, cross-checked with an independent implementation), `rolling_ols` without
  look-ahead, `factor_exposures` (CAPM, FF3, FF5, momentum), `stationary_bootstrap`.
- `core.returns.convert_return_currency` and the Developed/Europe Ken French factor files.
- `examples/factor_exposures.py`, with an integration test.
- `examples/portfolio_toy.py`: the hand-reconciled toy portfolio end to end, with an
  integration test.
- `data.user_csv.parse_decimal` for exact money and quantities.
- `examples/m1_analytics_core.py`: end-to-end M1 example on synthetic data, with an
  integration test.
- Dev dependency `scipy-stubs`.
- `data.user_csv.parse_number`, shared by the CSV readers.
- Design notes `docs/design/1.1-core.md`, `1.2-data.md` and `1.3-instruments.md`;
  `docs/IDEAS.md` for out-of-scope ideas.
- Dev dependency `pandas-stubs`, so mypy strict type-checks pandas code.

### Changed

- Roadmap: FRED dropped (its terms prohibit storing or caching data); ECB Data Portal used for
  rates and inflation. Broker transaction import moved from 1.2 to 2.1.
- Layering: `instruments` may import `data` (documented exception); `portfolio` may import
  `core`, `data`, `instruments` and `metrics`.
- Test helpers live in `tests/support` (pytest `pythonpath` and mypy path include `tests/`).
- CSV mappings accept a thousands separator equal to the delimiter (quoted numbers).
- pytest uses `--import-mode=importlib`, so test files in different folders may share names.
- `build_portfolio_report` requires `checks` (a `CheckResult` or `None`) and `lookthrough`
  (a `LookThroughInputs` or `None`).
- `CheckContext` requires a `lookthrough` input (`None` makes those checks not applicable).
- Layering: `lookthrough` may import `core`, `data`, `instruments`, `metrics` and
  `portfolio`; `checks` may also import `lookthrough`; `reporting` may import `checks` and
  `lookthrough`.

## [0.1.0] - 2026-11-10

### Added

- Project skeleton with `src/` layout and the `qrlab` package: documented stubs for `core`,
  `data`, `stats`, `metrics`, `validation`, `backtest` and `reporting`.
- Layering test (`tests/unit/test_architecture.py`) enforcing downward-only dependencies.
- Package and installation smoke tests; seeded `rng` fixture for deterministic tests.
- Tooling: uv with `uv.lock`, Ruff (lint and format), mypy (strict), pytest with warnings as
  errors and coverage; LF line endings enforced by `.gitattributes`.
- `.gitignore` that excludes everything under `data/` except its README.
- GitHub Actions CI on Linux and Windows for Python 3.11 and 3.13.
- Project documentation: `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`.

[Unreleased]: https://github.com/alessandroszn/quant-research-lab/compare/v1.0.0rc1...HEAD
[1.0.0rc1]: https://github.com/alessandroszn/quant-research-lab/compare/v0.4.0...v1.0.0rc1
[0.4.0]: https://github.com/alessandroszn/quant-research-lab/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/alessandroszn/quant-research-lab/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alessandroszn/quant-research-lab/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alessandroszn/quant-research-lab/releases/tag/v0.1.0
