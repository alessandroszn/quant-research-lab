# Ideas

Out-of-scope ideas, triaged at each milestone. Nothing here is planned until it moves into
`ROADMAP.md`.

| Idea | Raised in | Notes |
|---|---|---|
| Exchange calendars (NYSE, Xetra, Borsa Italiana, LSE) | 1.1 `core` | Needs a reliable source of exchange holidays and early closes; until then, `BusinessCalendar` with user-supplied holidays covers them. |
| Pre-2002 TARGET closing days | 1.1 `core` | 1999–2001 had extra closing days (e.g. 31 December); only needed for euro data before 2002. |
| Complete ISO 4217 table | 1.1 `core` | `MINOR_UNITS` lists 36 common currencies; extend from the official ISO list when a portfolio needs others. |
| FRED as a data source | 1.2 `data` | Excluded: its terms prohibit storing or caching data without written consent. Reconsider only with written permission or a no-cache design. |
| Ken French portfolio files | 1.2 `data` | 25/100 size–value portfolios, industry portfolios; multi-table files. Add when a study (5.3) needs them. |
| Retry with back-off for downloads | 1.2 `data` | The ECB Data Portal intermittently returns HTTP 504; today a failed download raises and nothing is stored. |
| Country name to ISO code table | 1.3 `instruments` | Issuer holdings files use country names ("United States"); needed for look-through in 2.5. |
| Issuer holdings adapters (iShares, Xtrackers, Vanguard, Amundi, SPDR, Invesco) | 1.3 `instruments` | Each needs its own terms-of-use review before any download code. |
| Exchange listings and trading currencies | 1.3 `instruments` | Needed when valuing transactions on a specific exchange (2.1). |
| FIFO and specific-lot cost basis | 2.1 `portfolio` | Average cost (Italian regime amministrato) is implemented; other methods for other tax regimes. |
| Original cost on transfers in | 2.1 `portfolio` | Transfers in take market value as cost basis; carrying the original cost from another broker matters for taxes. |
| Percentage contribution linking (Carino, GRAP) | 2.1 `portfolio` | Planned with attribution (4.4); money contribution by position exists. |
