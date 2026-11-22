"""Detection and selection of useful stars (SPEC 5.1)."""

from dataclasses import dataclass

import numpy as np
from astropy.stats import sigma_clipped_stats
from numpy.typing import NDArray
from photutils.detection import DAOStarFinder


@dataclass(frozen=True)
class SelectionConfig:
    detection_sigma: float = 10.0
    fwhm_guess_px: float = 4.0
    isolation_fwhm: float = 5.0
    edge_px: int = 20
    saturation_radius_px: int = 3
    sharp_low: float = 0.2
    sharp_high: float = 1.0


@dataclass(frozen=True)
class Candidate:
    x: float
    y: float
    peak: float
    rejected: str | None  # None if the star is usable


def find_stars(
    image: NDArray[np.float64],
    saturated: NDArray[np.bool_],
    config: SelectionConfig | None = None,
) -> list[Candidate]:
    """All detections, each marked usable or with the reason it was rejected."""
    config = config or SelectionConfig()
    _, median, std = sigma_clipped_stats(image, sigma=3.0)
    finder = DAOStarFinder(
        fwhm=config.fwhm_guess_px,
        threshold=config.detection_sigma * std,
        sharplo=-10.0,
        sharphi=10.0,
        roundlo=-10.0,
        roundhi=10.0,
        exclude_border=False,
    )
    table = finder(image - median)
    if table is None or len(table) == 0:
        return []

    # photutils 3 renamed the centroid columns; accept both spellings.
    x_name = "x_centroid" if "x_centroid" in table.colnames else "xcentroid"
    y_name = "y_centroid" if "y_centroid" in table.colnames else "ycentroid"
    xs = np.asarray(table[x_name], dtype=float)
    ys = np.asarray(table[y_name], dtype=float)
    sharp = np.asarray(table["sharpness"], dtype=float)
    peaks = np.asarray(table["peak"], dtype=float)
    height, width = image.shape
    min_separation = config.isolation_fwhm * config.fwhm_guess_px
    r = config.saturation_radius_px

    candidates: list[Candidate] = []
    for i, (x, y) in enumerate(zip(xs, ys, strict=True)):
        reason: str | None = None
        xi, yi = round(x), round(y)
        distances = np.hypot(xs - x, ys - y)
        distances[i] = np.inf
        if (
            x < config.edge_px
            or y < config.edge_px
            or x > width - 1 - config.edge_px
            or y > height - 1 - config.edge_px
        ):
            reason = "edge"
        elif saturated[max(yi - r, 0) : yi + r + 1, max(xi - r, 0) : xi + r + 1].any():
            reason = "saturated"
        elif distances.min() < min_separation:
            reason = "crowded"
        elif not config.sharp_low <= sharp[i] <= config.sharp_high:
            reason = "not_compact"
        candidates.append(Candidate(float(x), float(y), float(peaks[i]), reason))
    return candidates
