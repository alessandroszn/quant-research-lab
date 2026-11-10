"""Time-aware model validation.

Planned contents: expanding- and rolling-window walk-forward splits, purged and
embargoed splits for overlapping labels. Random shuffled splits are deliberately
not provided. Every split guarantees ``max(train_time) < min(test_time)``.
"""
