# data/

Local, git-ignored data store. Nothing in this folder except this README is committed.

- `raw/` — source files exactly as downloaded. Read-only by convention; never edited in place.
- `interim/` — cleaned or aligned intermediates, always reproducible from `raw/` by code.
- `processed/` — final research datasets.

Each dataset should have a sidecar note recording source, licence, download date, date range,
and whether prices are total-return (dividend-adjusted) or price-only.
