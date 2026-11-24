"""Per-star and per-frame measurements (SPEC 5.2 to 5.4)."""

import math
from dataclasses import dataclass

import numpy as np
from astropy.stats import sigma_clipped_stats
from numpy.typing import NDArray
from scipy.optimize import least_squares

from gtc_iq.stars import Candidate, SelectionConfig, find_stars
from gtc_iq.synthetic import elliptical_moffat, fwhm_from_alpha

MIN_STARS = 5
MAX_HALF_PX = 40
# Physical limits of the fit: Moffat alpha 0.5-30 px (FWHM about 0.5-30 px) and beta 1.2-10.
ALPHA_RANGE = (0.5, 30.0)
BETA_RANGE = (1.2, 10.0)
CENTRE_TOLERANCE_PX = 3.0
CORE_RADIUS_PX = 6.0
# Pixels closer than this to another detected source are left out of the fit. At 3 FWHM the
# wings of a Moffat with beta 2.5 are below 0.3 % of its peak.
NEIGHBOUR_MASK_FWHM = 3.0
BACKGROUND_ZONES = 8


@dataclass(frozen=True)
class StarMeasurement:
    x: float
    y: float
    fwhm_px: float  # geometric mean of major and minor axes (Moffat fit)
    fwhm_major_px: float
    fwhm_minor_px: float
    fwhm_gauss_px: float
    ellipticity_fit: float
    ellipticity_moments: float
    theta_rad: float
    beta: float


@dataclass(frozen=True)
class FrameMeasurement:
    n_detected: int
    n_used: int
    rejected: dict[str, int]
    fwhm_px: float | None
    fwhm_mad_px: float | None
    fwhm_arcsec: float | None
    fwhm_gauss_px: float | None
    ellipticity: float | None
    ellipticity_moments: float | None
    background_adu: float
    background_noise_adu: float
    saturated_fraction: float
    stars: list[StarMeasurement]


def _cutout(
    image: NDArray[np.float64], x: float, y: float, half: int
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    xi, yi = round(x), round(y)
    y0, y1 = max(yi - half, 0), min(yi + half + 1, image.shape[0])
    x0, x1 = max(xi - half, 0), min(xi + half + 1, image.shape[1])
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
    return image[y0:y1, x0:x1], xx, yy


def moments_ellipticity(
    stamp: NDArray[np.float64], xx: NDArray[np.float64], yy: NDArray[np.float64], sigma: float
) -> float:
    """Ellipticity 1 - b/a from Gaussian-weighted second moments.

    Plain moments are dominated by noise in the wings; a round Gaussian window of the size of
    the star keeps them stable. The window makes the result slightly rounder than the truth,
    which is why the fit-based ellipticity is the main measure (SPEC 5.3 and decision log).
    """
    weights = np.exp(-((xx - xx.mean()) ** 2 + (yy - yy.mean()) ** 2) / (2 * sigma**2))
    xc, yc = float(xx.mean()), float(yy.mean())
    for _ in range(10):
        w = np.clip(stamp, 0, None) * weights
        total = w.sum()
        if total <= 0:
            return float("nan")
        xc, yc = float((w * xx).sum() / total), float((w * yy).sum() / total)
        weights = np.exp(-((xx - xc) ** 2 + (yy - yc) ** 2) / (2 * sigma**2))
    w = np.clip(stamp, 0, None) * weights
    total = w.sum()
    mxx = float((w * (xx - xc) ** 2).sum() / total)
    myy = float((w * (yy - yc) ** 2).sum() / total)
    mxy = float((w * (xx - xc) * (yy - yc)).sum() / total)
    root = math.sqrt(((mxx - myy) / 2) ** 2 + mxy**2)
    major, minor = (mxx + myy) / 2 + root, (mxx + myy) / 2 - root
    if minor <= 0:
        return float("nan")
    return 1 - math.sqrt(minor / major)


def _shape_guess(
    data: NDArray[np.float64],
    xx: NDArray[np.float64],
    yy: NDArray[np.float64],
    x_det: float,
    y_det: float,
) -> tuple[float, float, float, float, float]:
    """Centre, axes and angle from the moments of the bright core, used as fit start.

    Only pixels near the detection count: in crowded fields the brightest pixel of the cutout
    is often another star, and starting from it the fit ends on that star or on a limit.
    """
    near = np.hypot(xx - x_det, yy - y_det) <= CORE_RADIUS_PX
    peak = float(data[near].max())
    core = np.where(near & (data > 0.1 * peak), data, 0.0)
    total = core.sum()
    xc, yc = float((core * xx).sum() / total), float((core * yy).sum() / total)
    mxx = float((core * (xx - xc) ** 2).sum() / total)
    myy = float((core * (yy - yc) ** 2).sum() / total)
    mxy = float((core * (xx - xc) * (yy - yc)).sum() / total)
    root = math.sqrt(((mxx - myy) / 2) ** 2 + mxy**2)
    major = math.sqrt(max((mxx + myy) / 2 + root, 0.25))
    minor = math.sqrt(max((mxx + myy) / 2 - root, 0.25))
    theta = 0.5 * math.atan2(2 * mxy, mxx - myy)
    return xc, yc, major, minor, theta


def _fit_moffat(
    stamp: NDArray[np.float64],
    xx: NDArray[np.float64],
    yy: NDArray[np.float64],
    x_det: float,
    y_det: float,
    keep: NDArray[np.bool_],
) -> NDArray[np.float64] | None:
    """Fit an elliptical Moffat plus a constant background to the kept pixels of a cutout."""
    edge = np.concatenate([stamp[0], stamp[-1], stamp[:, 0], stamp[:, -1]])
    data = stamp - float(np.median(edge))
    near = np.hypot(xx - x_det, yy - y_det) <= CORE_RADIUS_PX
    if not near.any():
        return None
    peak = float(data[near].max())
    if peak <= 0:
        return None
    xc, yc, major, minor, theta = _shape_guess(data, xx, yy, x_det, y_det)
    beta0 = 2.5
    # Core moments of a Moffat behave roughly like a Gaussian sigma: FWHM ~ 2.3548 sigma.
    a0 = max(2.3548 * major, 1.0) / (2 * math.sqrt(2 ** (1 / beta0) - 1))
    b0 = max(2.3548 * minor, 1.0) / (2 * math.sqrt(2 ** (1 / beta0) - 1))

    def residuals(p: NDArray[np.float64]) -> NDArray[np.float64]:
        amp, x0, y0, log_a, log_b, th, log_beta1, bkg = p
        model = elliptical_moffat(
            xx, yy, amp, x0, y0, math.exp(log_a), math.exp(log_b), th, 1 + math.exp(log_beta1)
        )
        result: NDArray[np.float64] = (model + bkg - data)[keep]
        return result

    lo_a, hi_a = math.log(ALPHA_RANGE[0]), math.log(ALPHA_RANGE[1])
    lo_b, hi_b = math.log(BETA_RANGE[0] - 1), math.log(BETA_RANGE[1] - 1)
    tol = CENTRE_TOLERANCE_PX
    lower = np.array([0.0, x_det - tol, y_det - tol, lo_a, lo_a, -np.inf, lo_b, -np.inf])
    upper = np.array([np.inf, x_det + tol, y_det + tol, hi_a, hi_a, np.inf, hi_b, np.inf])
    start = np.array([peak, xc, yc, math.log(a0), math.log(b0), theta, math.log(beta0 - 1), 0.0])
    start = np.clip(start, lower + 1e-9, upper - 1e-9)
    fit = least_squares(residuals, start, bounds=(lower, upper), method="trf", max_nfev=500)
    if not fit.success:
        return None
    # A fit that ends on a limit is not a measurement: the star is blended, saturated or not a star.
    span = upper[1:7] - lower[1:7]
    at_limit = np.isfinite(span) & (
        (fit.x[1:7] - lower[1:7] < 1e-3 * span) | (upper[1:7] - fit.x[1:7] < 1e-3 * span)
    )
    return None if at_limit.any() else np.asarray(fit.x)


def _keep_mask(
    xx: NDArray[np.float64],
    yy: NDArray[np.float64],
    neighbours: NDArray[np.float64],
    radius: float,
) -> NDArray[np.bool_]:
    keep = np.ones(xx.shape, dtype=bool)
    for nx, ny in neighbours:
        keep &= np.hypot(xx - nx, yy - ny) > radius
    return keep


def measure_star(
    image: NDArray[np.float64],
    x: float,
    y: float,
    half: int = 20,
    neighbours: NDArray[np.float64] | None = None,
    fwhm_guess_px: float = 4.0,
) -> StarMeasurement | None:
    """Fit one star detected at (x, y), ignoring the pixels around other detected sources.

    The cutout grows if the star turns out to be large (wings beyond 3 FWHM).
    """
    others = np.empty((0, 2)) if neighbours is None else np.asarray(neighbours, dtype=float)
    radius = NEIGHBOUR_MASK_FWHM * fwhm_guess_px
    params = None
    for _ in range(3):
        stamp, xx, yy = _cutout(image, x, y, half)
        reach = half + radius
        local = others[(np.abs(others[:, 0] - x) <= reach) & (np.abs(others[:, 1] - y) <= reach)]
        keep = _keep_mask(xx, yy, local, radius)
        params = _fit_moffat(stamp, xx, yy, x, y, keep)
        if params is None:
            return None
        major_fwhm = fwhm_from_alpha(math.exp(max(params[3], params[4])), 1 + math.exp(params[6]))
        needed = math.ceil(4 * major_fwhm)
        if needed <= half or half >= MAX_HALF_PX:
            break
        half = min(needed, MAX_HALF_PX)
    assert params is not None
    edge = np.concatenate([stamp[0], stamp[-1], stamp[:, 0], stamp[:, -1]])
    data = stamp - float(np.median(edge))
    peak = float(params[0])
    _, x0, y0, log_a, log_b, theta, log_beta1, _ = params
    beta = 1 + math.exp(log_beta1)
    a, b = math.exp(log_a), math.exp(log_b)
    if b > a:
        a, b, theta = b, a, theta + math.pi / 2
    major, minor = fwhm_from_alpha(a, beta), fwhm_from_alpha(b, beta)
    fwhm = math.sqrt(major * minor)

    def gauss_residuals(p: NDArray[np.float64]) -> NDArray[np.float64]:
        amp, gx, gy, log_s, bkg = p
        s = math.exp(log_s)
        model = amp * np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / (2 * s**2))
        result: NDArray[np.float64] = (model + bkg - data)[keep]
        return result

    g_lower = np.array([0.0, x0 - 3, y0 - 3, math.log(0.2), -np.inf])
    g_upper = np.array([np.inf, x0 + 3, y0 + 3, math.log(30.0), np.inf])
    g_start = np.clip(
        np.array([peak, x0, y0, math.log(fwhm / 2.3548), 0.0]), g_lower + 1e-9, g_upper - 1e-9
    )
    gfit = least_squares(gauss_residuals, g_start, bounds=(g_lower, g_upper), method="trf")
    fwhm_gauss = 2.3548 * math.exp(gfit.x[3])
    e_moments = moments_ellipticity(data, xx, yy, sigma=fwhm / 2.3548)
    return StarMeasurement(
        x=float(x0),
        y=float(y0),
        fwhm_px=fwhm,
        fwhm_major_px=major,
        fwhm_minor_px=minor,
        fwhm_gauss_px=fwhm_gauss,
        ellipticity_fit=1 - minor / major,
        ellipticity_moments=e_moments,
        theta_rad=float(math.remainder(theta, math.pi)),
        beta=beta,
    )


def _median_mad(values: list[float]) -> tuple[float, float]:
    arr = np.asarray(values)
    median = float(np.median(arr))
    return median, float(1.4826 * np.median(np.abs(arr - median)))


def zone_background(
    image: NDArray[np.float64], zones: int = BACKGROUND_ZONES
) -> tuple[float, float]:
    """Sky level and noise as medians over a grid of zones.

    Without a flat the vignetting makes the sky level vary across the detector, and a single
    global standard deviation measures that slope as if it were noise. Each zone is small enough
    for the sky to be flat inside it.
    """
    levels: list[float] = []
    noises: list[float] = []
    for rows in np.array_split(np.arange(image.shape[0]), zones):
        for cols in np.array_split(np.arange(image.shape[1]), zones):
            zone = image[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
            _, level, noise = sigma_clipped_stats(zone, sigma=3.0)
            levels.append(float(level))
            noises.append(float(noise))
    return float(np.median(levels)), float(np.median(noises))


def measure_frame(
    image: NDArray[np.float64],
    saturated: NDArray[np.bool_],
    pixel_scale_arcsec: float,
    config: SelectionConfig | None = None,
) -> FrameMeasurement:
    config = config or SelectionConfig()
    background, noise = zone_background(image)
    candidates: list[Candidate] = find_stars(image, saturated, config)
    rejected: dict[str, int] = {}
    stars: list[StarMeasurement] = []
    positions = np.array([(c.x, c.y) for c in candidates], dtype=float).reshape(-1, 2)
    for i, c in enumerate(candidates):
        if c.rejected is not None:
            rejected[c.rejected] = rejected.get(c.rejected, 0) + 1
            continue
        measured = measure_star(
            image,
            c.x,
            c.y,
            neighbours=np.delete(positions, i, axis=0),
            fwhm_guess_px=config.fwhm_guess_px,
        )
        if measured is None:
            rejected["fit_failed"] = rejected.get("fit_failed", 0) + 1
        else:
            stars.append(measured)

    enough = len(stars) >= MIN_STARS
    fwhm, fwhm_mad = _median_mad([s.fwhm_px for s in stars]) if enough else (None, None)
    return FrameMeasurement(
        n_detected=len(candidates),
        n_used=len(stars),
        rejected=rejected,
        fwhm_px=fwhm,
        fwhm_mad_px=fwhm_mad,
        fwhm_arcsec=fwhm * pixel_scale_arcsec if fwhm is not None else None,
        fwhm_gauss_px=float(np.median([s.fwhm_gauss_px for s in stars])) if enough else None,
        ellipticity=float(np.median([s.ellipticity_fit for s in stars])) if enough else None,
        ellipticity_moments=float(np.nanmedian([s.ellipticity_moments for s in stars]))
        if enough
        else None,
        background_adu=float(background),
        background_noise_adu=float(noise),
        saturated_fraction=float(saturated.mean()),
        stars=stars,
    )
