# Running the CI checks locally

`scripts/ci_local.sh` runs the steps of the CI workflow (`.github/workflows/ci.yml`) on your
own machine, in the same order (design note 10.1). It is the way to check Linux when CI cannot
run, for example when a private repository has used up its Actions minutes. A test keeps the
script's commands equal to the workflow's.

The script runs on a **fresh clone**, never on your working folder. A clone holds only
committed files, as CI does, so it never sees `data/` or files you have not committed.

## On Linux, with WSL on Windows

1. **Install Ubuntu** (once). In a PowerShell window run as administrator:

   ```
   wsl --install -d Ubuntu-24.04
   ```

   Then create the Linux user it asks for. Use the Ubuntu release that GitHub's
   `ubuntu-latest` runner uses.

2. **Install git and the Qt system libraries** the app tests need (once), in the Ubuntu
   window:

   ```
   sudo apt-get update && sudo apt-get install -y git libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3
   ```

3. **Install uv** (once), from [Astral's instructions](https://docs.astral.sh/uv/getting-started/installation/).

4. **Clone and run.** Clone into the Linux file system, not under `/mnt/c`:

   ```
   git -c safe.directory='*' clone --upload-pack="git -c safe.directory='*' upload-pack" /mnt/c/PATH/TO/YOUR/CHECKOUT ~/qrlab-ci
   bash ~/qrlab-ci/scripts/ci_local.sh ~/qrlab-ci
   ```

   The checkout under `/mnt/c` belongs to your Windows user, so git refuses it as "dubious
   ownership". The two `safe.directory` settings allow it for this one clone, without
   changing your git configuration. Both are needed: the clone opens the source itself, and
   it starts `upload-pack` with the configuration cleared.

   For a later run, delete the folder and clone again.

## On Windows

The same script runs in Git Bash, on a clone in a temporary folder:

```
git clone . "$TEMP/qrlab-ci"
bash scripts/ci_local.sh "$TEMP/qrlab-ci"
```

## What it does not cover

- **The Windows app build** (`app-build.yml`) runs only in CI and in the release workflow.
- **CI itself.** The script is a faithful copy of the steps, not GitHub's runner: the first
  push after a local run still runs real CI.
