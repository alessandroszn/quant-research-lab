"""Data access, schema validation and point-in-time handling.

Invariants: raw source data is read-only and never mutated in place; every
observation carries the timestamp at which it became *available*, not only the
period it describes; survivorship-free universes and delisting returns are
represented explicitly; dividends/splits treatment (total vs. price return) is
declared, never implied.
"""
