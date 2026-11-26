"""Explainable quality-control rules (SPEC 6).

Every frame gets a list of flags, each with the rule name and a reason that quotes the measured
value and the threshold. Rules that compare with the rest of the night use the median and MAD of
the frames of the same filter and night, because conditions change from one night to the next.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np

from gtc_iq.config import QCConfig

MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class FrameQCInput:
    product_id: int
    status: str  # "ok" or "unmeasurable"
    reason: str
    filter: str | None
    date_obs: datetime | None
    exptime_s: float | None
    n_used: int
    fwhm_arcsec: float | None
    ellipticity: float | None
    background_adu: float | None
    saturated_fraction: float | None


@dataclass(frozen=True)
class Flag:
    rule: str
    reason: str


@dataclass(frozen=True)
class FrameQC:
    product_id: int
    flags: list[Flag]

    @property
    def passed(self) -> bool:
        return not self.flags


def night_of(moment: datetime) -> date:
    """Observing night, named after its evening: a frame taken after midnight belongs to the
    night that started the day before."""
    return (moment - timedelta(hours=12)).date()


def _median_mad(values: list[float]) -> tuple[float, float]:
    arr = np.asarray(values)
    median = float(np.median(arr))
    return median, float(MAD_TO_SIGMA * np.median(np.abs(arr - median)))


def _fmt(value: float) -> str:
    return f"{value:.4g}"


def apply_rules(frames: list[FrameQCInput], config: QCConfig) -> list[FrameQC]:
    flags: dict[int, list[Flag]] = {f.product_id: [] for f in frames}

    measured: list[FrameQCInput] = []
    for f in frames:
        if f.status != "ok":
            flags[f.product_id].append(Flag("unmeasurable", f.reason or "frame not measured"))
            continue
        saturated = f.saturated_fraction
        if saturated is not None and saturated > config.max_saturated_fraction:
            flags[f.product_id].append(
                Flag(
                    "saturation",
                    f"saturated pixels {saturated:.2%} > "
                    f"{config.max_saturated_fraction:.2%}: exposure too long for the field",
                )
            )
        if f.n_used < config.min_stars or f.fwhm_arcsec is None:
            flags[f.product_id].append(
                Flag(
                    "few_stars",
                    f"{f.n_used} usable stars < {config.min_stars}: "
                    "clouds, defocus or a poor field",
                )
            )
            continue
        if f.ellipticity is not None and f.ellipticity > config.max_ellipticity:
            flags[f.product_id].append(
                Flag(
                    "high_ellipticity",
                    f"ellipticity {_fmt(f.ellipticity)} > {_fmt(config.max_ellipticity)}: "
                    "possible guiding or tracking problem",
                )
            )
        measured.append(f)

    groups: dict[tuple[str, date], list[FrameQCInput]] = defaultdict(list)
    for f in measured:
        assert f.filter is not None and f.date_obs is not None
        groups[(f.filter, night_of(f.date_obs))].append(f)

    for (filter_name, night), members in groups.items():
        if len(members) < config.min_group_frames:
            continue
        where = f"{filter_name} on the night of {night.isoformat()}"
        fwhm_median, fwhm_mad = _median_mad([m.fwhm_arcsec for m in members if m.fwhm_arcsec])
        limit = fwhm_median + config.fwhm_outlier_mad * fwhm_mad
        for m in members:
            assert m.fwhm_arcsec is not None
            if fwhm_mad > 0 and m.fwhm_arcsec > limit:
                flags[m.product_id].append(
                    Flag(
                        "fwhm_outlier",
                        f'FWHM {m.fwhm_arcsec:.2f}" > {limit:.2f}" (median {fwhm_median:.2f}" '
                        f"+ {_fmt(config.fwhm_outlier_mad)} MAD of {where}): "
                        "image quality worse than the rest of the night",
                    )
                )

        # Background is compared per second, so frames of different exposure time can share
        # a group.
        rates = {
            m.product_id: m.background_adu / m.exptime_s
            for m in members
            if m.background_adu is not None and m.exptime_s
        }
        if len(rates) < config.min_group_frames:
            continue
        bkg_median, bkg_mad = _median_mad(list(rates.values()))
        bkg_limit = bkg_median + config.background_outlier_mad * bkg_mad
        for product_id, rate in rates.items():
            if bkg_mad > 0 and rate > bkg_limit:
                flags[product_id].append(
                    Flag(
                        "bright_background",
                        f"sky background {rate:.1f} ADU/s > {bkg_limit:.1f} ADU/s (median "
                        f"{bkg_median:.1f} + {_fmt(config.background_outlier_mad)} MAD of "
                        f"{where}): Moon, twilight or lit clouds",
                    )
                )

    return [FrameQC(f.product_id, flags[f.product_id]) for f in frames]
