# Windows build

How the Windows program and installer are made (design note
`docs/design/6.2-windows-build.md`). The build normally runs in GitHub Actions
(`.github/workflows/app-build.yml`); these are the same steps by hand.

## What gets built

The program is one folder, `dist/Quant Research Lab/`, holding two programs that share one set
of libraries:

| File | What it is |
|---|---|
| `QuantResearchLab.exe` | the desktop app; `--self-test WORKSPACE` runs every config of a workspace without showing a window |
| `qrlab.exe` | the command line (`qrlab run CONFIG`, …) |
| `build-info.json` | commit, build time, Python and package versions; the runner records the commit from here |
| `THIRD_PARTY_NOTICES.txt` | the licence texts of everything shipped |
| `licences/` | the LGPL-3.0 and GPL-3.0 texts that apply to Qt and PySide6 |

From that folder the build makes:

- `QuantResearchLab-<version>-win64-setup.exe`: the per-user installer, which needs no
  administrator rights;
- `QuantResearchLab-<version>-win64.zip`: the same folder, portable;
- `SHA256SUMS.txt`: the hashes of both.

## Build locally

These commands run in PowerShell from the repository root, on a **clean** checkout.
`build_info.py` refuses a tree with uncommitted changes.

1. Install the locked environment and build the folder:

   ```bash
   uv sync --locked --extra app --extra parquet --group build
   uv run python packaging/build_info.py build-info.json
   uv run pyinstaller --noconfirm --clean packaging/qrlab.spec
   ```

2. Put the build info, the notices and the licence texts next to the programs:

   ```bash
   Move-Item build-info.json "dist/Quant Research Lab/"
   uv run python packaging/notices.py "dist/Quant Research Lab/THIRD_PARTY_NOTICES.txt"
   Copy-Item -Recurse packaging/licences "dist/Quant Research Lab/licences"
   ```

3. Optional: build the installer. This needs Inno Setup 6.7.1.

   ```bash
   & "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=<version> packaging\installer.iss
   ```

## What CI checks

1. **Same results as the source.** CI copies the six `configs/experiments/example_*.toml`
   and their synthetic data into two folders (`examples_tree.py`). It runs them with
   `uv run qrlab` and with the frozen `qrlab.exe`. Then `compare_runs.py` requires
   byte-identical outputs and identical scalars; it ignores only the times, the paths and the
   code-version block.
2. **The frozen app's self-test.** CI runs `QuantResearchLab.exe --self-test` on the examples
   workspace. Its outputs must match the source run too.
3. **Installer round trip.** CI installs silently, runs the **installed** app's self-test,
   uninstalls silently, and checks two things: the program folder is gone, and the workspace
   and its results are still there.

## Decisions

- **One folder, not one file.** Qt's DLLs stay separate files that a user can replace, as the
  LGPL requires for dynamic linking. The program also starts faster, and false positives from
  antivirus software are rarer.
- **No UPX compression.** Compressed executables trigger antivirus heuristics more often.
- **Licence texts.**
  - The PySide6 wheels carry only Qt's commercial licence file, but they are used under the
    LGPL. `licences/` therefore holds unchanged copies of the LGPL-3.0 and GPL-3.0 texts,
    taken from <https://www.gnu.org/licenses/> on 2026-11-13. The LGPL-3.0 builds on the
    GPL-3.0, so both texts are needed. Their SHA-256 hashes are checked by a test:

    | File | SHA-256 |
    |---|---|
    | `lgpl-3.0.txt` | `e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118` |
    | `gpl-3.0.txt` | `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986` |

  - Every other bundled distribution must ship its own licence file, or the build stops
    (`notices.py`).
  - PyInstaller is listed because its bootloader is inside each executable. Its own
    dependencies are build tools and are not shipped.
- **Inno Setup licence.** Inno Setup is free. Its authors ask commercial users to buy a
  commercial licence. This is a personal, non-commercial research project. Inno Setup is a
  build tool and is not shipped in the program.
- **Pinned Inno Setup.** The workflow installs Inno Setup 6.7.1 with Chocolatey and checks the
  version, because future Windows runner images may not include it.
- **Not code-signed.** Windows SmartScreen warns before the first start of an unsigned
  program. Users can check the SHA-256 instead. Signing is a paid service; see
  `docs/IDEAS.md`.
- **What is reproducible.** The commit in `build-info.json`, the locked versions, and results
  identical to the source. Executables are not bit-for-bit reproducible, because they carry
  timestamps.
