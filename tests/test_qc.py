from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from gtc_iq.config import QCConfig, load_config
from gtc_iq.qc import Flag, FrameQC, FrameQCInput, apply_rules, night_of

START = datetime(2025, 7, 20, 0, 54)


def _frame(
    product_id: int,
    *,
    fwhm: float = 1.05,
    ellipticity: float = 0.08,
    background: float = 8000.0,
    exptime: float = 50.0,
    filter_name: str = "Sloan_z",
    n_used: int = 300,
    saturated: float = 0.001,
    status: str = "ok",
    reason: str = "",
    when: datetime | None = None,
) -> FrameQCInput:
    return FrameQCInput(
        product_id=product_id,
        status=status,
        reason=reason,
        filter=filter_name,
        date_obs=when or START + timedelta(minutes=2 * product_id),
        exptime_s=exptime,
        n_used=n_used,
        fwhm_arcsec=fwhm if n_used >= 5 else None,
        ellipticity=ellipticity,
        background_adu=background,
        saturated_fraction=saturated,
    )


def _night(n: int = 10) -> list[FrameQCInput]:
    # Small, realistic scatter so the MAD is not zero.
    return [
        _frame(i, fwhm=1.0 + 0.01 * (i % 5), background=8000.0 + 40 * (i % 4)) for i in range(n)
    ]


def _rules(results: list[FrameQC], product_id: int) -> list[Flag]:
    return next(r for r in results if r.product_id == product_id).flags


def _names(results: list[FrameQC], product_id: int) -> list[str]:
    return [flag.rule for flag in _rules(results, product_id)]


def test_a_normal_night_passes() -> None:
    results = apply_rules(_night(), QCConfig())
    assert all(r.passed for r in results)


def test_each_rule_flags_its_case_with_the_value_in_the_reason() -> None:
    frames = _night()
    frames += [
        _frame(20, fwhm=1.60),
        _frame(21, ellipticity=0.28),
        _frame(22, background=12000.0),
        _frame(23, saturated=0.025),
        _frame(24, n_used=3),
        _frame(25, status="unmeasurable", reason="missing key AIRMASS"),
    ]
    results = apply_rules(frames, QCConfig())
    assert _names(results, 20) == ["fwhm_outlier"]
    assert _names(results, 21) == ["high_ellipticity"]
    assert _names(results, 22) == ["bright_background"]
    assert _names(results, 23) == ["saturation"]
    assert _names(results, 24) == ["few_stars"]
    assert _names(results, 25) == ["unmeasurable"]
    assert '1.60"' in _rules(results, 20)[0].reason
    assert "0.28 > 0.2" in _rules(results, 21)[0].reason
    assert "2.50% > 2.00%" in _rules(results, 23)[0].reason
    assert "3 usable stars" in _rules(results, 24)[0].reason
    assert _rules(results, 25)[0].reason == "missing key AIRMASS"
    assert all(r.passed for r in results if r.product_id < 20)


def test_outliers_are_judged_within_their_own_filter() -> None:
    # The i-band frames are all broader than the z-band ones, as expected from the wavelength
    # dependence. Compared with their own filter, none of them is an outlier.
    frames = _night()
    frames += [
        _frame(30 + i, fwhm=1.20 + 0.01 * (i % 5), filter_name="Sloan_i", exptime=100.0)
        for i in range(6)
    ]
    assert all(r.passed for r in apply_rules(frames, QCConfig()))


def test_background_is_compared_per_second() -> None:
    # Same sky rate, twice the exposure: not a bright background.
    frames = _night()
    frames.append(_frame(40, background=16080.0, exptime=100.0))
    assert _names(apply_rules(frames, QCConfig()), 40) == []


def test_small_groups_skip_the_night_relative_rules() -> None:
    frames = [_frame(i, fwhm=1.0 + 0.01 * i) for i in range(3)] + [_frame(9, fwhm=3.0)]
    results = apply_rules(frames, QCConfig())
    assert all(r.passed for r in results)


def test_night_is_named_after_its_evening() -> None:
    assert night_of(datetime(2025, 7, 20, 2, 22)) == date(2025, 7, 19)
    assert night_of(datetime(2025, 7, 19, 21, 0)) == date(2025, 7, 19)


def test_frames_of_different_nights_are_not_mixed() -> None:
    frames = _night()
    other_night = START + timedelta(days=1)
    frames += [
        _frame(50 + i, fwhm=1.5 + 0.01 * (i % 5), when=other_night + timedelta(minutes=i))
        for i in range(6)
    ]
    assert all(r.passed for r in apply_rules(frames, QCConfig()))


def test_config_reads_yaml_and_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("qc:\n  max_ellipticity: 0.15\n", encoding="utf-8")
    assert load_config(path).max_ellipticity == 0.15
    assert load_config(path).min_stars == 5

    path.write_text("qc:\n  max_elipticity: 0.15\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_repository_config_matches_the_defaults() -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config.yaml"
    assert load_config(repo_config) == QCConfig()


def test_reason_shows_enough_digits_to_tell_value_and_threshold_apart() -> None:
    # Found with real data: an ellipticity of 0.2003 was reported as "0.2 > 0.2".
    frames = [*_night(), _frame(70, ellipticity=0.2003)]
    [flag] = _rules(apply_rules(frames, QCConfig()), 70)
    assert "0.2003 > 0.2" in flag.reason
