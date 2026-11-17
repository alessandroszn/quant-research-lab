"""Run the desktop app with ``python -m qrlab_app``."""

from qrlab_app.app import main

if __name__ == "__main__":  # a run's child process imports this module without opening the app
    raise SystemExit(main())
