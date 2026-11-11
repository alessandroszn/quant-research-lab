"""Look-through inputs bundled for the health checks and the report."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from qrlab.core.errors import ValidationError
from qrlab.instruments.holdings import HoldingsSnapshot
from qrlab.instruments.identifiers import Isin
from qrlab.lookthrough.exposures import LookThrough
from qrlab.lookthrough.overlap import Overlap, pairwise_overlaps
from qrlab.lookthrough.tracking import TrackingSeries

__all__ = ["LookThroughInputs"]


@dataclass(frozen=True)
class LookThroughInputs:
    """Exposures with the holdings and tracking series they come from.

    Parameters
    ----------
    exposures
        Look-through of the portfolio (:func:`~qrlab.lookthrough.look_through`).
    snapshots
        The holdings used for ``exposures``: exactly the funds it looked through.
    tracking
        ``(fund series, index series)`` by fund ISIN, for the funds with tracking data.
    """

    exposures: LookThrough
    snapshots: Mapping[Isin, HoldingsSnapshot]
    tracking: Mapping[Isin, tuple[TrackingSeries, TrackingSeries]]

    def __post_init__(self) -> None:
        """Check that the snapshots are the ones the exposures were built from."""
        used = {isin: s.as_of for isin, s in self.snapshots.items()}
        if used != dict(self.exposures.snapshot_dates):
            raise ValidationError("snapshots must be exactly the holdings used for the exposures")

    def overlaps(self) -> list[Overlap]:
        """Pairwise overlap of the funds looked through, with the exposures' weight treatment."""
        return pairwise_overlaps(dict(self.snapshots), treatment=self.exposures.treatment)
