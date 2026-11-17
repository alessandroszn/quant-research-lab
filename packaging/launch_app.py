"""Entry point of QuantResearchLab.exe (the desktop app, or ``--self-test WORKSPACE``).

Runs start in child processes of this program (design note 12.2b); ``freeze_support`` lets a
child of the frozen program run its run instead of opening another window.
"""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from qrlab_app.app import main

    raise SystemExit(main())
