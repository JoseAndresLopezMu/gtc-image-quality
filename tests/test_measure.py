import math

import numpy as np
import pytest

from gtc_iq.measure import MIN_STARS, measure_frame, measure_star
from gtc_iq.stars import SelectionConfig, find_stars
from gtc_iq.synthetic import StarSpec, make_frame, star_model

FWHM_TOLERANCE = 0.05  # SPEC 7
ELLIPTICITY_TOLERANCE = 0.02  # SPEC 7


def test_star_model_conserves_flux() -> None:
    star = StarSpec(100, 100, flux_e=1e5, fwhm_major_px=4, ellipticity=0.2, theta_rad=0.7)
    # The Moffat wings extend far; a 400 px box keeps the missing flux below 1 %.
    assert star_model((201, 201), star).sum() == pytest.approx(1e5, rel=0.01)


@pytest.mark.parametrize("fwhm", [2.0, 3.0, 5.0, 8.0])
@pytest.mark.parametrize("ellipticity", [0.0, 0.1, 0.2, 0.3])
def test_single_star_meets_spec_tolerances(fwhm: float, ellipticity: float) -> None:
    for seed in range(4):
        theta = 0.3 + 0.4 * seed
        star = StarSpec(60.3, 59.6, 2e5, fwhm, ellipticity, theta)
        measured = measure_star(make_frame((120, 120), [star], seed=seed), 60, 60)
        assert measured is not None
        true_fwhm = fwhm * math.sqrt(1 - ellipticity)  # geometric mean of the axes
        assert measured.fwhm_px == pytest.approx(true_fwhm, rel=FWHM_TOLERANCE)
        assert measured.ellipticity_fit == pytest.approx(ellipticity, abs=ELLIPTICITY_TOLERANCE)


def test_angle_of_elongated_star() -> None:
    star = StarSpec(60, 60, 2e5, 5.0, 0.3, theta_rad=0.6)
    measured = measure_star(make_frame((120, 120), [star], seed=1), 60, 60)
    assert measured is not None
    assert measured.theta_rad == pytest.approx(0.6, abs=0.05)


def _field(
    n: int, fwhm: float, ellipticity: float, seed: int = 0
) -> tuple[list[StarSpec], np.ndarray]:
    rng = np.random.default_rng(seed)
    side = math.ceil(math.sqrt(n))
    spacing = 60
    stars = [
        StarSpec(
            40 + spacing * (i % side) + rng.uniform(-3, 3),
            40 + spacing * (i // side) + rng.uniform(-3, 3),
            rng.uniform(5e4, 3e5),
            fwhm,
            ellipticity,
            theta_rad=0.4,
        )
        for i in range(n)
    ]
    size = 80 + spacing * side
    return stars, make_frame((size, size), stars, seed=seed)


def test_frame_median_fwhm_and_ellipticity() -> None:
    _, image = _field(16, fwhm=5.0, ellipticity=0.15)
    result = measure_frame(image, np.zeros(image.shape, dtype=bool), pixel_scale_arcsec=0.2544)
    assert result.n_used == 16
    true_fwhm = 5.0 * math.sqrt(1 - 0.15)
    assert result.fwhm_px == pytest.approx(true_fwhm, rel=FWHM_TOLERANCE)
    assert result.fwhm_arcsec == pytest.approx(true_fwhm * 0.2544, rel=FWHM_TOLERANCE)
    assert result.ellipticity == pytest.approx(0.15, abs=ELLIPTICITY_TOLERANCE)
    assert result.background_adu == pytest.approx(200 / 1.9, rel=0.02)


def test_frame_without_stars_is_not_measured() -> None:
    image = make_frame((300, 300), [], seed=0)
    result = measure_frame(image, np.zeros(image.shape, dtype=bool), pixel_scale_arcsec=0.2544)
    assert result.n_used == 0
    assert result.fwhm_px is None and result.ellipticity is None


def test_too_few_stars_gives_no_median() -> None:
    _, image = _field(MIN_STARS - 1, fwhm=4.0, ellipticity=0.0)
    result = measure_frame(image, np.zeros(image.shape, dtype=bool), pixel_scale_arcsec=0.2544)
    assert result.n_used == MIN_STARS - 1
    assert result.fwhm_px is None


def test_rejects_edge_saturated_and_crowded_stars() -> None:
    stars = [
        StarSpec(150, 150, 2e5, 4.0),  # good
        StarSpec(8, 150, 2e5, 4.0),  # edge
        StarSpec(150, 60, 2e5, 4.0),  # saturated (mask below)
        # Pair 12 px apart (3 FWHM): resolved as two detections, closer than 5 FWHM.
        # Pairs closer than about 1.5 FWHM blend into a single detection (SPEC 11).
        StarSpec(244, 250, 2e5, 4.0),
        StarSpec(256, 250, 2e5, 4.0),
    ]
    image = make_frame((320, 320), stars, seed=3)
    saturated = np.zeros(image.shape, dtype=bool)
    saturated[60, 150] = True
    reasons = {
        (round(c.x), round(c.y)): c.rejected
        for c in find_stars(image, saturated, SelectionConfig())
    }
    assert reasons[(150, 150)] is None
    assert reasons[(8, 150)] == "edge"
    assert reasons[(150, 60)] == "saturated"
    assert len([1 for (x, y) in reasons if 240 <= x <= 260 and 245 <= y <= 255]) == 2
    crowded = [r for (x, y), r in reasons.items() if 240 <= x <= 260 and 245 <= y <= 255]
    assert crowded and all(r == "crowded" for r in crowded)
