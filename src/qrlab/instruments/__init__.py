"""Instrument master data and fund holdings snapshots.

Identifiers are validated (ISIN check digits, ISO country codes); unknown values are ``None``
rather than defaults; incomplete or stale records produce explicit findings instead of being
filled in.
"""
