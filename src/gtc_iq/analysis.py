"""Image quality against airmass, wavelength and observing conditions (SPEC 5.5).

Turbulence theory predicts FWHM proportional to airmass^0.6 and to wavelength^-0.2. The fits
here check whether the measured FWHM follows those laws and document where it does not. The
conditions in the header (wind, elevation, focus) are only explored with rank correlations:
with a few nights they cannot separate causes, because they all drift with time.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
from scipy import stats

from gtc_iq.qc import night_of

AIRMASS_EXPONENT = 0.6
WAVELENGTH_EXPONENT = -0.2

# Central wavelengths at 0 degrees from the OSIRIS+ broad-band imaging table,
# https://www.gtc.iac.es/instruments/osiris+/osiris+.php (read on 2026-11-26). Not in the header.
FILTER_WAVELENGTH_NM = {"Sloan_i": 770.5, "Sloan_z": 969.5}

CONDITIONS = {
    "wind_speed_ms": "Velocidad del viento (m/s)",
    "wind_dir_deg": "Dirección del viento (°)",
    "elevation_deg": "Elevación (°)",
    "focus": "Foco AG1FOCUS",
    "humidity_pct": "Humedad (%)",
}


@dataclass(frozen=True)
class FrameRecord:
    """One measured frame, as read from frames.csv and qc.csv."""

    product_id: int
    filter: str
    date_obs: datetime
    airmass: float
    fwhm_arcsec: float
    ellipticity: float | None
    conditions: dict[str, float | None]
    passed: bool = True

    @property
    def night(self) -> date:
        return night_of(self.date_obs)

    @property
    def hours_into_night(self) -> float:
        """Hours since noon of the day the night started, so nights can be compared."""
        noon = datetime.combine(self.night, datetime.min.time()) + timedelta(hours=12)
        return (self.date_obs - noon).total_seconds() / 3600


@dataclass(frozen=True)
class SlopeFit:
    """Power-law fit FWHM = A * airmass^slope, by least squares in log-log."""

    filter: str
    method: str  # "pooled" or "within_night"
    n_frames: int
    n_nights: int
    airmass_min: float
    airmass_max: float
    slope: float
    ci_low: float
    ci_high: float

    @property
    def contains_theory(self) -> bool:
        return self.ci_low <= AIRMASS_EXPONENT <= self.ci_high

    @property
    def expected_change(self) -> float:
        """Relative FWHM change that theory predicts across the airmass range."""
        return float((self.airmass_max / self.airmass_min) ** AIRMASS_EXPONENT - 1)


@dataclass(frozen=True)
class WavelengthCheck:
    """FWHM ratio between two filters, from frames close in time and corrected to zenith."""

    short_filter: str
    long_filter: str
    n_pairs: int
    observed_ratio: float
    observed_error: float
    expected_ratio: float


@dataclass(frozen=True)
class Correlation:
    filter: str
    variable: str
    n_frames: int
    rho_fwhm: float
    p_value: float
    rho_time: float  # the same variable against the hour of the night: does it drift?


def usable(frames: Iterable[FrameRecord]) -> list[FrameRecord]:
    """Frames that passed quality control: flagged frames stay out of every fit."""
    return [f for f in frames if f.passed]


def _by_filter(frames: Iterable[FrameRecord]) -> dict[str, list[FrameRecord]]:
    groups: dict[str, list[FrameRecord]] = defaultdict(list)
    for frame in frames:
        groups[frame.filter].append(frame)
    return dict(sorted(groups.items()))


def _ols_slope(x: np.ndarray, y: np.ndarray, dof: int) -> tuple[float, float, float]:
    """Slope of y on x (both already centred if needed) with its 95 % interval."""
    sxx = float(np.sum(x * x))
    slope = float(np.sum(x * y) / sxx)
    residuals = y - slope * x
    sigma2 = float(np.sum(residuals**2) / dof)
    half = float(stats.t.ppf(0.975, dof)) * (sigma2 / sxx) ** 0.5
    return slope, slope - half, slope + half


def _fit(name: str, method: str, frames: list[FrameRecord]) -> SlopeFit | None:
    log_am = np.log([f.airmass for f in frames])
    log_fwhm = np.log([f.fwhm_arcsec for f in frames])
    nights = [f.night for f in frames]
    if method == "pooled":
        x, y = log_am - log_am.mean(), log_fwhm - log_fwhm.mean()
        dof = len(frames) - 2
    else:
        # A free intercept per night: only the change of airmass within each night counts,
        # so night-to-night changes of the turbulence do not enter the slope.
        x, y = log_am.copy(), log_fwhm.copy()
        for night in set(nights):
            members = np.array([n == night for n in nights])
            x[members] -= x[members].mean()
            y[members] -= y[members].mean()
        dof = len(frames) - len(set(nights)) - 1
    if dof < 1 or float(np.sum(x * x)) == 0:
        return None
    slope, low, high = _ols_slope(x, y, dof)
    return SlopeFit(
        filter=name,
        method=method,
        n_frames=len(frames),
        n_nights=len(set(nights)),
        airmass_min=float(np.exp(log_am.min())),
        airmass_max=float(np.exp(log_am.max())),
        slope=slope,
        ci_low=low,
        ci_high=high,
    )


def fit_airmass(frames: Iterable[FrameRecord]) -> list[SlopeFit]:
    """Pooled and within-night slope of log FWHM against log airmass, per filter."""
    fits: list[SlopeFit] = []
    for name, members in _by_filter(usable(frames)).items():
        for method in ("pooled", "within_night"):
            fit = _fit(name, method, members)
            if fit is not None:
                fits.append(fit)
    return fits


def zenith_fwhm(frame: FrameRecord) -> float:
    """FWHM corrected to airmass 1 with the theoretical exponent."""
    return float(frame.fwhm_arcsec / frame.airmass**AIRMASS_EXPONENT)


def wavelength_check(
    frames: Iterable[FrameRecord],
    short_filter: str = "Sloan_i",
    long_filter: str = "Sloan_z",
    max_gap: timedelta = timedelta(minutes=10),
) -> WavelengthCheck | None:
    """Median FWHM ratio long/short of frames taken within max_gap of each other.

    Pairing frames close in time removes most of the change of the turbulence during the night,
    which is much larger than the wavelength effect (about 5 % between i and z).
    """
    groups = _by_filter(usable(frames))
    shorts, longs = groups.get(short_filter, []), groups.get(long_filter, [])
    ratios: list[float] = []
    for frame in longs:
        nearest = min(shorts, key=lambda s: abs(s.date_obs - frame.date_obs), default=None)
        if nearest is not None and abs(nearest.date_obs - frame.date_obs) <= max_gap:
            ratios.append(zenith_fwhm(frame) / zenith_fwhm(nearest))
    if len(ratios) < 3:
        return None
    values = np.asarray(ratios)
    median = float(np.median(values))
    # Standard error of the median from the MAD, for roughly normal scatter.
    sigma = 1.4826 * float(np.median(np.abs(values - median)))
    expected = float(
        (FILTER_WAVELENGTH_NM[long_filter] / FILTER_WAVELENGTH_NM[short_filter])
        ** WAVELENGTH_EXPONENT
    )
    return WavelengthCheck(
        short_filter=short_filter,
        long_filter=long_filter,
        n_pairs=len(ratios),
        observed_ratio=median,
        observed_error=1.2533 * sigma / len(ratios) ** 0.5,
        expected_ratio=expected,
    )


def _spearman(x: list[float], y: list[float]) -> tuple[float, float]:
    if len(set(x)) < 2 or len(set(y)) < 2:
        return float("nan"), float("nan")
    result = stats.spearmanr(x, y)
    return float(result.statistic), float(result.pvalue)


def correlations(
    frames: Iterable[FrameRecord],
    variables: Iterable[str] = CONDITIONS,
    value: Callable[[FrameRecord], float] = zenith_fwhm,
) -> list[Correlation]:
    """Spearman correlation of each condition with the zenith-corrected FWHM, per filter."""
    out: list[Correlation] = []
    for name, members in _by_filter(usable(frames)).items():
        for variable in variables:
            pairs = [
                (cond, value(f), f.hours_into_night)
                for f in members
                if (cond := f.conditions.get(variable)) is not None
            ]
            if len(pairs) < 5:
                continue
            xs, ys, ts = (list(column) for column in zip(*pairs, strict=True))
            rho, p_value = _spearman(xs, ys)
            rho_time, _ = _spearman(xs, ts)
            out.append(Correlation(name, variable, len(pairs), rho, p_value, rho_time))
    return out
