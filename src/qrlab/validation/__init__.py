"""Time-aware model validation: walk-forward splits with purging and embargo.

Random shuffled splits are deliberately not provided. Every split guarantees that every
training label ends strictly before the first test time.
"""

from qrlab.validation.splits import Split, Splits, expanding_splits, rolling_splits, take

__all__ = ["Split", "Splits", "expanding_splits", "rolling_splits", "take"]
