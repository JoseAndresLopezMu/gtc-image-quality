"""Synthetic frames with stars of known FWHM and ellipticity (SPEC 7)."""

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class StarSpec:
    x: float
    y: float
    flux_e: float
    fwhm_major_px: float
    ellipticity: float = 0.0  # 1 - minor/major
    theta_rad: float = 0.0  # angle of the major axis from +x
    beta: float = 2.5


def alpha_from_fwhm(fwhm: float, beta: float) -> float:
    return fwhm / (2 * math.sqrt(2 ** (1 / beta) - 1))


def fwhm_from_alpha(alpha: float, beta: float) -> float:
    return 2 * alpha * math.sqrt(2 ** (1 / beta) - 1)


def elliptical_moffat(
    xx: NDArray[np.float64],
    yy: NDArray[np.float64],
    amplitude: float,
    x0: float,
    y0: float,
    alpha_major: float,
    alpha_minor: float,
    theta: float,
    beta: float,
) -> NDArray[np.float64]:
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx, dy = xx - x0, yy - y0
    u = dx * cos_t + dy * sin_t
    v = -dx * sin_t + dy * cos_t
    r2 = (u / alpha_major) ** 2 + (v / alpha_minor) ** 2
    result: NDArray[np.float64] = amplitude * (1 + r2) ** (-beta)
    return result


def star_model(shape: tuple[int, int], star: StarSpec) -> NDArray[np.float64]:
    """Noiseless star in electrons, sampled at pixel centres, normalised to its total flux."""
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]].astype(np.float64)
    a = alpha_from_fwhm(star.fwhm_major_px, star.beta)
    b = a * (1 - star.ellipticity)
    amplitude = star.flux_e * (star.beta - 1) / (math.pi * a * b)
    return elliptical_moffat(xx, yy, amplitude, star.x, star.y, a, b, star.theta_rad, star.beta)


def make_frame(
    shape: tuple[int, int],
    stars: list[StarSpec],
    sky_e: float = 200.0,
    read_noise_e: float = 4.3,
    gain_e_per_adu: float = 1.9,
    saturation_adu: float | None = None,
    seed: int = 0,
) -> NDArray[np.float64]:
    """Bias-subtracted frame in ADU with Poisson and read noise.

    Default read noise and gain are those of the OSIRIS+ header (SPEC 4.4).
    """
    rng = np.random.default_rng(seed)
    electrons = np.full(shape, sky_e, dtype=np.float64)
    for star in stars:
        electrons += star_model(shape, star)
    noisy = rng.poisson(electrons).astype(np.float64) + rng.normal(0, read_noise_e, shape)
    adu = noisy / gain_e_per_adu
    if saturation_adu is not None:
        adu = np.minimum(adu, saturation_adu)
    return adu
