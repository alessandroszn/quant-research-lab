# Data sources and their terms

Quant Research Lab reads public data and your own files. Its rules for data:

- **Raw files are never modified.** Every download is stored byte for byte with its provenance:
  source, dataset, URL, download time, SHA-256, size and terms of use.
- **Parsers are strict.** They never guess formats: dates, separators, units and currencies
  are declared.
- **Downloading and parsing are separate.** Downloading is an explicit step; runs and parsers
  never use the network.
- **Terms are checked first.** The terms of use of a source are checked and recorded before it
  is added. The decisions are below.

## Public sources

| Source | Data | Terms (as recorded with every download) |
|---|---|---|
| Kenneth R. French Data Library | Fama-French factors, momentum, portfolios, international factors | Copyright Eugene F. Fama and Kenneth R. French; no licence published. Used locally for research with citation; raw files are not redistributed. |
| European Central Bank (ECB Data Portal) | Euro reference FX rates, €STR, euro-area HICP, AAA government yield curve | Free reuse if reproduced accurately, with the ECB cited as source. |
| Open Source Asset Pricing (Chen and Zimmermann) | Long-short returns of published predictors and their documentation, release 2026.10 at a pinned revision | CC BY 4.0. Cite Chen and Zimmermann (2022), *Critical Finance Review*. Raw files are not redistributed. |

**Excluded:** FRED. Its terms prohibit storing or caching data without written consent, and
the raw store keeps every vintage.

## Your own files

Your files are read only through explicit mappings, so nothing about their format is guessed:

- transactions in qrlab's own layout, the native file, with no mapping
  ({py:func}`qrlab.portfolio.parse_native_csv`; phase 8.8). You can write it by hand or let
  qrlab write it ({py:func}`qrlab.portfolio.write_native_csv`). A starting position is one
  `transfer_in` per fund, at the market price on the start date, with your original cost per
  unit in `cost`;
- broker exports (transactions), through {py:func}`qrlab.portfolio.load_broker_mapping`;
- price files, through {py:func}`qrlab.data.load_csv_mapping`;
- fund holdings, through {py:func}`qrlab.instruments.load_holdings_mapping`, as CSV or Excel
  (xlsx), with country codes or country names
  ({py:func}`qrlab.instruments.parse_holdings_file`);
- issuer maps (`isin,issuer`), through {py:func}`qrlab.instruments.load_issuer_map`.

**Issuer files** (holdings and NAV history from iShares, Vanguard and others) are downloaded by
you, for your own analysis, from the issuer's website. A first look at the terms, on
2026-11-15, found that the websites allow personal, non-commercial use, and that BlackRock's
US iShares terms forbid robots and automated copying. qrlab therefore never downloads them. qrlab has no code that downloads them, and they are
never redistributed: they stay in `data/`, and tests use synthetic files with the same
layout. The terms of each issuer's website are reviewed in full before a mapping file for its
layout is added to `configs/csv_mappings/`.

**Exchange prices** (Borsa Italiana, Xetra): no free history download with clear terms was
found, so none is added. A fund's prices come from its issuer's NAV history, downloaded by
you.

{py:func}`qrlab.data.import_local_file` copies a file into the raw store with its provenance.

Real portfolio data belongs only in the git-ignored `data/` folder, or in a desktop-app workspace
you choose. It never goes into tests, examples or published reports. The examples in
`examples/data/` are synthetic, and their ISINs are invented.
