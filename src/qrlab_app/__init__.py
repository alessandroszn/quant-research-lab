"""Desktop app for the Quant Research Lab: a thin layer over ``qrlab.experiments``.

The app edits, validates and runs experiment configs and shows the outputs the runner writes.
It contains no financial logic and imports only ``qrlab.experiments`` and ``qrlab.reporting``
from the library (enforced by a test). State lives in Qt-free view-models
(:mod:`qrlab_app.viewmodels`); widgets only display it.

Design note: ``docs/design/6.1-desktop-app.md``. Install with the ``app`` extra; start with
``qrlab-app``.
"""
