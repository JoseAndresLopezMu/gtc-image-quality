import math

import numpy as np
import pytest

from gtc_iq.measure import MIN_STARS, measure_frame, measure_star, zone_background
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


@pytest.mark.parametrize(("dx", "dy", "flux"), [(24, 5, 6e5), (22, -14, 4e5), (-18, -18, 1e6)])
@pytest.mark.parametrize("fwhm", [3.0, 5.0])
def test_brighter_neighbour_inside_cutout_is_ignored(
    dx: float, dy: float, flux: float, fwhm: float
) -> None:
    # A brighter star beyond the isolation radius still falls inside the cutout. The fit must
    # measure the detected star, not drift to the neighbour or end on a limit.
    target = StarSpec(70.3, 69.6, 2e5, fwhm, 0.1, 0.5)
    neighbour = StarSpec(70 + dx, 70 + dy, flux, fwhm, 0.1, 0.5)
    image = make_frame((160, 160), [target, neighbour], seed=2)
    measured = measure_star(image, 70.3, 69.6, neighbours=np.array([[neighbour.x, neighbour.y]]))
    assert measured is not None
    assert (measured.x, measured.y) == pytest.approx((70.3, 69.6), abs=0.2)
    assert measured.fwhm_px == pytest.approx(fwhm * math.sqrt(0.9), rel=FWHM_TOLERANCE)
    assert measured.ellipticity_fit == pytest.approx(0.1, abs=ELLIPTICITY_TOLERANCE)


def test_frame_with_bright_neighbours_keeps_its_stars() -> None:
    stars = [StarSpec(60 + 90 * i, 80, 2e5, 4.0, 0.1, 0.5) for i in range(6)]
    stars += [StarSpec(s.x + 23, s.y + 6, 8e5, 4.0, 0.1, 0.5) for s in stars]
    image = make_frame((180, 640), stars, seed=4)  # (height, width)
    result = measure_frame(image, np.zeros(image.shape, dtype=bool), pixel_scale_arcsec=0.2544)
    assert result.rejected.get("fit_failed", 0) == 0
    assert result.n_used == 12
    assert result.fwhm_px == pytest.approx(4.0 * math.sqrt(0.9), rel=FWHM_TOLERANCE)


def test_background_noise_ignores_a_smooth_gradient() -> None:
    # Sky falling by 10 % across the frame, as with vignetting before flat fielding. A single
    # global standard deviation counts that slope as noise (about 42 ADU here instead of 30).
    rng = np.random.default_rng(5)
    _, xx = np.mgrid[0:400, 0:400]
    sky = 1000.0 * (1 - 0.1 * xx / 400)
    image = sky + rng.normal(0, 30.0, sky.shape)
    level, noise = zone_background(image)
    assert noise == pytest.approx(30.0, rel=0.05)
    assert level == pytest.approx(float(np.median(sky)), rel=0.01)
    assert float(np.std(image)) > 1.3 * 30.0
