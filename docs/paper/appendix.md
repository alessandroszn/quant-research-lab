# Appendix A: reproducibility

Each study is a config in `configs/studies/`, run by the experiment runner of Quant Research
Lab. The runner writes a `record.json` holding:

- the config and its hash;
- the inputs with their SHA-256 hashes;
- the code version and the number of configurations tried;
- every output with its sample tag (in-sample, out-of-sample or descriptive).

The values below are read from those records. Every run of a study used the same code, inputs
and date, so one row per study suffices.

| Study | Run date | qrlab | Commit | Uncommitted changes | Seed | Configurations tried |
|---|---|---|---|---|---|---:|
| 1. Volatility-managed factors | {{ a_s1_date }} | {{ a_s1_version }} | {{ a_s1_commit }} | {{ a_s1_dirty }} | {{ a_s1_seed }} | {{ a_s1_tried }} |
| 2. 1/N against optimised portfolios | {{ a_s2_date }} | {{ a_s2_version }} | {{ a_s2_commit }} | {{ a_s2_dirty }} | {{ a_s2_seed }} | {{ a_s2_tried }} |
| 3. The factor zoo | {{ a_s3_date }} | {{ a_s3_version }} | {{ a_s3_commit }} | {{ a_s3_dirty }} | {{ a_s3_seed }} | {{ a_s3_tried }} |
| 4. Rebalancing for a EUR ETF investor | {{ a_s4_date }} | {{ a_s4_version }} | {{ a_s4_commit }} | {{ a_s4_dirty }} | {{ a_s4_seed }} | {{ a_s4_tried }} |

**A clean re-run.** The studies were first run on 2026-11-12, from a working tree whose records
flag uncommitted changes. That flag counts any change or untracked file in the checkout, so it
cannot tell which code ran. To settle it, every config was re-run on {{ a_s1_date }} from a
clean checkout of commit {{ a_s1_commit }}, with the same data files and trial ledgers.

Every output of every run was **byte-identical** to the first run: tables, scalars, figures and
reports, as checked with `packaging/compare_runs.py`. The table above and every number in this
paper come from the records of the clean re-run.

**Configurations tried** counts the distinct configs run under each study's name. It includes
the robustness configs reported in each study, and it enters the deflated Sharpe ratios of
studies 1 and 2.

## Data files

The raw files are not redistributed; see Appendix B. These are the exact files used, as
recorded; the file name holds the download time and the start of the SHA-256.

**Study 1** (Kenneth R. French Data Library):

```{include} _generated/a_s1_inputs.md
```

**Study 2** (Kenneth R. French Data Library):

```{include} _generated/a_s2_inputs.md
```

**Study 3** (Open Source Asset Pricing, release 2026.10):

```{include} _generated/a_s3_inputs.md
```

**Study 4** (Kenneth R. French Data Library and European Central Bank):

```{include} _generated/a_s4_inputs.md
```

## How to rerun

```bash
uv sync --extra parquet
uv run qrlab run configs/studies/volatility_managed_paper.toml
```

`docs/guides/reproducing-studies.md` explains how to download the same data vintages into the
raw store and how to compare hashes.

# Appendix B: data terms

- **Kenneth R. French Data Library.** Copyright Eugene F. Fama and Kenneth R. French; no licence
  is published. Used locally for research, with citation; raw files are not redistributed.
- **European Central Bank Data Portal.** Free reuse if reproduced accurately, with the ECB
  cited as source.
- **Open Source Asset Pricing** (Chen and Zimmermann, 2022). CC BY 4.0. Raw files are not
  redistributed.
