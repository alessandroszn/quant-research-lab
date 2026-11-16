# Installation

Quant Research Lab needs Python 3.11 or newer. It runs on Windows, macOS and Linux. The
desktop app is packaged for Windows only, as an installer.

## As a library

Version 1.0.0 is installed from the wheel attached to its GitHub release; it is not on PyPI
yet.

```bash
pip install "quant-research-lab @ https://github.com/alessandroszn/quant-research-lab/releases/download/v1.0.0/quant_research_lab-1.0.0-py3-none-any.whl"
```

There are two optional extras:

| Extra | Adds | Needed for |
|---|---|---|
| `app` | PySide6-Essentials (Qt, LGPL-3.0) | the desktop app, `qrlab-app` |
| `parquet` | pyarrow | reading Parquet files (study 3, Open Source Asset Pricing data) |

```bash
pip install "quant-research-lab[app,parquet] @ https://github.com/alessandroszn/quant-research-lab/releases/download/v1.0.0/quant_research_lab-1.0.0-py3-none-any.whl"
```

The import name is `qrlab`. Two commands are installed:

- `qrlab`, the command line;
- `qrlab-app`, the desktop app (needs the `app` extra).

## From the source

Development uses [uv](https://docs.astral.sh/uv/) and the locked dependency versions in
`uv.lock`:

```bash
git clone https://github.com/alessandroszn/quant-research-lab.git
cd quant-research-lab
uv sync
uv run qrlab kinds
```

The quality gate that every change must pass:

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
```

## The Windows app

1. Download `QuantResearchLab-<version>-win64-setup.exe` and `SHA256SUMS.txt` from the release.
2. Check the file hash in PowerShell:

   ```bash
   Get-FileHash QuantResearchLab-<version>-win64-setup.exe -Algorithm SHA256
   ```

   It must match the line in `SHA256SUMS.txt`.
3. Run the installer. It installs for your user only, without administrator rights, into
   `%LOCALAPPDATA%\Programs\Quant Research Lab`.

The program is not code-signed, so Windows SmartScreen may show "Windows protected your PC".
Choose *More info*, then *Run anyway*, after checking the hash.

A portable zip of the same folder is also available, and needs no installation.

Uninstalling removes only the program folder. It keeps:

- your workspaces;
- the settings file, `%APPDATA%\qrlab\qrlab-app.ini`.
