# Reproducing the studies

The four studies in {doc}`../studies/index` were run on public data through the experiment
runner. Their configs are in `configs/studies/`. Each report lists:

- the exact data files, with their download date and SHA-256;
- the commit of the code;
- the number of configurations tried.

To reproduce a study:

1. Download the same datasets into a raw store.
2. Point the config's inputs at them.
3. Run the config.

## 1. Download the data

Raw files are kept unchanged, with provenance, in a {py:class}`qrlab.data.RawStore`. By
convention the store is the git-ignored `data/raw/` folder. Downloading is always a separate
step from running, and the runner never touches the network.

```python
from datetime import UTC, datetime
from pathlib import Path

from qrlab.data import (
    OSAP_REVISION,
    RawStore,
    UrlFetcher,
    download_ecb_fx,
    download_ecb_series,
    download_ken_french,
    download_osap,
)

store = RawStore(Path("data/raw"))
fetcher = UrlFetcher(timeout_seconds=60)
now = lambda: datetime.now(UTC)

download_ken_french(fetcher, store, "F-F_Research_Data_Factors_daily", now=now)  # study 1
download_ecb_fx(fetcher, store, now=now)  # study 4
download_ecb_series(fetcher, store, "yc_aaa_spot_6y", now=now)  # study 4
download_osap(fetcher, store, "long_short_returns", revision=OSAP_REVISION, now=now)  # study 3
```

Where to find the dataset names:

- the inputs of each config in `configs/studies/`;
- {py:data}`qrlab.data.KEN_FRENCH_DATASETS`, {py:data}`qrlab.data.ECB_SERIES` and
  {py:data}`qrlab.data.OSAP_FILES`;
- the "Data" section of each report.

Each download is stored under `data/raw/<source>/<dataset>/` as a new **vintage**, named by its
download time and hash, next to a JSON provenance file.

## 2. Point the config at your files

The configs name the vintages used for the reports, such as
`data/raw/osap/long_short_returns/20261112T161458Z_fc01df25d438.parquet`. If you downloaded
later, the file names differ, so update the paths under `[inputs]`.

The data providers may also have revised their files since. Ken French's library in particular
updates its history. Compare the SHA-256 in the report with your file's: equal hashes mean the
same data.

## 3. Run

```bash
uv run qrlab validate configs/studies/volatility_managed_paper.toml
uv run qrlab run configs/studies/volatility_managed_paper.toml
```

With the same data and the same code, the outputs are identical. Studies 1, 2 and 4 draw random
numbers for their bootstraps: they need a `seed`, which is in their configs. Two caveats:

- **Optional extras.** Study 3 reads Parquet files and needs the `parquet` extra.
- **Run time.** The studies can take several minutes, most of all the bootstraps of studies 1
  and 2.

## Terms of use

The raw files are never committed or redistributed: only results derived from them are
published. See {doc}`data-sources` for each provider's terms.
