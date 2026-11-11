# Ideas

Out-of-scope ideas, triaged at each milestone. Nothing here is planned until it moves into
`ROADMAP.md`.

| Idea | Raised in | Notes |
|---|---|---|
| Exchange calendars (NYSE, Xetra, Borsa Italiana, LSE) | 1.1 `core` | Needs a reliable source of exchange holidays and early closes; until then, `BusinessCalendar` with user-supplied holidays covers them. |
| Pre-2002 TARGET closing days | 1.1 `core` | 1999–2001 had extra closing days (e.g. 31 December); only needed for euro data before 2002. |
| Complete ISO 4217 table | 1.1 `core` | `MINOR_UNITS` lists 36 common currencies; extend from the official ISO list when a portfolio needs others. |
