# PyInstaller spec: one folder, two programs sharing the same libraries (design note 6.2).
#
#   QuantResearchLab.exe  windowed desktop app (qrlab_app), also `--self-test WORKSPACE`
#   qrlab.exe             console command line (qrlab.cli)
#
# Build from the repository root, in the locked environment:
#   uv sync --locked --extra app --extra parquet --group build
#   uv run pyinstaller --noconfirm --clean packaging/qrlab.spec
# The folder appears in dist/Quant Research Lab/. build-info.json and the notices are added
# next to the programs afterwards (see packaging/README.md).

from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is defined by PyInstaller

# The runner records these versions through importlib.metadata (experiments.runner): without
# their metadata a frozen run would fail.
METADATA = ["quant-research-lab", "numpy", "pandas", "scipy", "statsmodels", "matplotlib"]
datas = [item for name in METADATA for item in copy_metadata(name)]
# The window's icon (design note 12.4), next to the app's modules as in the source tree.
datas.append((str(ROOT / "src" / "qrlab_app" / "resources" / "qrlab.png"), "qrlab_app/resources"))
ICON = str(ROOT / "packaging" / "qrlab.ico")

# Never needed at run time; leaving them out keeps the bundle smaller.
EXCLUDES = [
    "tkinter",
    "_tkinter",
    "IPython",
    "jupyter_client",
    "notebook",
    "pytest",
    "sklearn",  # only used by tests, as an independent cross-check
    "matplotlib.backends.backend_tkagg",
]


def analysis(script: str) -> Analysis:  # noqa: F821 - Analysis is defined by PyInstaller
    return Analysis(  # noqa: F821
        [str(ROOT / "packaging" / script)],
        pathex=[str(ROOT / "src")],
        datas=datas,
        excludes=EXCLUDES,
        noarchive=False,
    )


gui = analysis("launch_app.py")
cli = analysis("launch_cli.py")

gui_exe = EXE(  # noqa: F821
    PYZ(gui.pure),  # noqa: F821
    gui.scripts,
    [],
    exclude_binaries=True,
    name="QuantResearchLab",
    icon=ICON,
    console=False,
    upx=False,
)
cli_exe = EXE(  # noqa: F821
    PYZ(cli.pure),  # noqa: F821
    cli.scripts,
    [],
    exclude_binaries=True,
    name="qrlab",
    icon=ICON,
    console=True,
    upx=False,
)
COLLECT(  # noqa: F821
    gui_exe,
    gui.binaries,
    gui.datas,
    cli_exe,
    cli.binaries,
    cli.datas,
    upx=False,
    name="Quant Research Lab",
)
