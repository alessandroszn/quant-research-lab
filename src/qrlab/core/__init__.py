"""Shared primitives with no dependencies on other ``qrlab`` subpackages.

Planned contents: frequency and annualisation conventions (periods per year are
explicit, never inferred silently), return-type definitions (simple vs. log),
input validation helpers (monotonic unique ``DatetimeIndex``, no duplicated
timestamps, explicit NaN policy) and common exception types.
"""
