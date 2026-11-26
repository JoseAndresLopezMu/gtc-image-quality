from datetime import datetime, timedelta

import numpy as np
import pytest

from gtc_iq.analysis import (
    AIRMASS_EXPONENT,
    FILTER_WAVELENGTH_NM,
    FrameRecord,
    correlations,
    fit_airmass,
    wavelength_check,
    zenith_fwhm,
)

START = datetime(2025, 7, 20, 0, 30)


def _frame(
    product_id: int,
    airmass: float,
    fwhm: float,
    *,
    filter_name: str = "Sloan_z",
    when: datetime | None = None,
    wind: float | None = 8.0,
    passed: bool = True,
) -> FrameRecord:
    return FrameRecord(
        product_id=product_id,
        filter=filter_name,
        date_obs=when or START + timedelta(minutes=2 * product_id),
        airmass=airmass,
        fwhm_arcsec=fwhm,
        ellipticity=0.07,
        conditions={"wind_speed_ms": wind, "focus": 12.0},
        passed=passed,
    )


def _theory_night(
    seeing: float, airmasses: np.ndarray, start: datetime, first_id: int, noise: float = 0.0
) -> list[FrameRecord]:
    rng = np.random.default_rng(first_id)
    return [
        _frame(
            first_id + i,
            float(am),
            float(seeing * am**AIRMASS_EXPONENT * (1 + noise * rng.standard_normal())),
            when=start + timedelta(minutes=3 * i),
        )
        for i, am in enumerate(airmasses)
    ]


def _fits(frames: list[FrameRecord]) -> dict[str, float]:
    return {fit.method: fit.slope for fit in fit_airmass(frames)}


def test_exact_power_law_gives_the_theoretical_slope() -> None:
    frames = _theory_night(0.9, np.linspace(1.05, 2.0, 12), START, 0)
    slopes = _fits(frames)
    assert slopes["pooled"] == pytest.approx(AIRMASS_EXPONENT, abs=1e-9)
    assert slopes["within_night"] == pytest.approx(AIRMASS_EXPONENT, abs=1e-9)


def test_noisy_power_law_interval_contains_the_theory() -> None:
    frames = _theory_night(0.9, np.linspace(1.05, 2.0, 40), START, 0, noise=0.03)
    pooled = next(fit for fit in fit_airmass(frames) if fit.method == "pooled")
    assert pooled.contains_theory
    assert pooled.ci_high - pooled.ci_low < 0.3
    assert pooled.expected_change == pytest.approx((2.0 / 1.05) ** 0.6 - 1)


def test_within_night_fit_ignores_a_change_of_seeing_between_nights() -> None:
    # Night 1 is good seeing at high airmass, night 2 bad seeing at low airmass. Pooling them
    # gives a negative slope; with one intercept per night the theory comes back.
    night1 = _theory_night(0.7, np.linspace(1.6, 2.0, 8), START, 0)
    night2 = _theory_night(1.4, np.linspace(1.05, 1.3, 8), START + timedelta(days=3), 100)
    slopes = _fits(night1 + night2)
    assert slopes["pooled"] < 0
    assert slopes["within_night"] == pytest.approx(AIRMASS_EXPONENT, abs=1e-9)


def test_flagged_frames_and_single_frames_stay_out() -> None:
    frames = _theory_night(0.9, np.linspace(1.1, 1.5, 6), START, 0)
    frames.append(_frame(50, 1.3, 5.0, passed=False))
    frames.append(_frame(60, 1.2, 1.0, filter_name="Sloan_i"))
    fits = fit_airmass(frames)
    assert {fit.filter for fit in fits} == {"Sloan_z"}
    assert all(fit.n_frames == 6 for fit in fits)
    assert _fits(frames)["pooled"] == pytest.approx(AIRMASS_EXPONENT, abs=1e-9)


def test_wavelength_ratio_of_interleaved_filters() -> None:
    expected = (FILTER_WAVELENGTH_NM["Sloan_z"] / FILTER_WAVELENGTH_NM["Sloan_i"]) ** -0.2
    frames: list[FrameRecord] = []
    for i in range(10):
        when = START + timedelta(minutes=4 * i)
        seeing = 1.0 + 0.05 * np.sin(i)  # the night changes, both filters follow it
        am_i, am_z = 1.20 + 0.02 * i, 1.21 + 0.02 * i
        frames.append(_frame(i, am_i, seeing * am_i**0.6, filter_name="Sloan_i", when=when))
        frames.append(
            _frame(
                100 + i,
                am_z,
                seeing * expected * am_z**0.6,
                when=when + timedelta(minutes=2),
            )
        )
    check = wavelength_check(frames)
    assert check is not None
    assert check.n_pairs == 10
    assert check.expected_ratio == pytest.approx(expected)
    assert check.observed_ratio == pytest.approx(expected, rel=1e-9)


def test_wavelength_ratio_needs_frames_close_in_time() -> None:
    frames = [_frame(i, 1.2, 1.0, filter_name="Sloan_i") for i in range(5)]
    later = START + timedelta(hours=3)
    frames += [_frame(100 + i, 1.2, 1.0, when=later + timedelta(minutes=i)) for i in range(5)]
    assert wavelength_check(frames) is None


def test_correlation_with_a_condition_and_with_time() -> None:
    # FWHM grows with the wind, and the wind rises during the night.
    frames = [_frame(i, 1.3, 1.0 + 0.02 * i, wind=5.0 + 0.3 * i) for i in range(10)]
    frames.append(_frame(20, 1.3, 1.1, wind=None))
    [wind] = [c for c in correlations(frames) if c.variable == "wind_speed_ms"]
    assert wind.n_frames == 10
    assert wind.rho_fwhm == pytest.approx(1.0)
    assert wind.rho_time == pytest.approx(1.0)
    assert wind.p_value < 0.01
    [focus] = [c for c in correlations(frames) if c.variable == "focus"]
    assert np.isnan(focus.rho_fwhm)  # constant focus says nothing


def test_zenith_correction() -> None:
    assert zenith_fwhm(_frame(1, 2.0, 2.0**0.6)) == pytest.approx(1.0)


def test_time_correlation_uses_the_hour_of_the_night_not_the_date() -> None:
    # Two nights months apart. In each one the wind drops during the night; the second night is
    # windier. The date would give a positive correlation; the hour of the night, a negative one.
    frames: list[FrameRecord] = []
    for night, base in ((datetime(2025, 3, 9, 21), 5.0), (datetime(2025, 7, 19, 21), 9.0)):
        frames += [
            _frame(len(frames), 1.3, 1.0, when=night + timedelta(hours=i), wind=base - 0.3 * i)
            for i in range(6)
        ]
    [wind] = [c for c in correlations(frames) if c.variable == "wind_speed_ms"]
    assert wind.rho_time < 0
