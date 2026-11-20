import math
import re
from datetime import datetime

from astropy.io.fits import Header
from pydantic import BaseModel

_SECTION = re.compile(r"^\[(\d+):(\d+),(\d+):(\d+)\]$")
_FILTER_KEYS = ("FILTER1", "FILTER2", "FILTER3", "FILTER4")
_EMPTY_FILTERS = {"", "OPEN"}


class HeaderError(ValueError):
    """The header lacks something needed to measure the frame (SPEC 4.4)."""


class Section(BaseModel):
    """A FITS image section, stored as 0-based half-open numpy indices."""

    y0: int
    y1: int
    x0: int
    x1: int

    @property
    def slices(self) -> tuple[slice, slice]:
        return slice(self.y0, self.y1), slice(self.x0, self.x1)


class FrameHeader(BaseModel):
    filter: str
    exptime_s: float
    airmass: float
    binning: tuple[int, int]
    pixel_scale_arcsec: float
    gain_e_per_adu: float
    read_noise_e: float
    bias_section: Section
    trim_section: Section
    date_obs: datetime
    object: str
    humidity_pct: float | None = None
    wind_speed_ms: float | None = None
    wind_dir_deg: float | None = None
    pressure_hpa: float | None = None
    elevation_deg: float | None = None
    azimuth_deg: float | None = None
    rotator_deg: float | None = None
    focus: float | None = None
    ccd_temp_k: float | None = None


def parse_section(value: str) -> Section:
    """Convert a FITS section such as '[26:2073,1:2056]' (1-based, inclusive, x first)."""
    match = _SECTION.match(value.strip())
    if match is None:
        raise HeaderError(f"invalid section {value!r}")
    x_start, x_end, y_start, y_end = (int(group) for group in match.groups())
    if x_start > x_end or y_start > y_end:
        raise HeaderError(f"invalid section {value!r}")
    return Section(y0=y_start - 1, y1=y_end, x0=x_start - 1, x1=x_end)


def parse_filter(header: Header) -> str:
    used = [
        str(header[key]).strip()
        for key in _FILTER_KEYS
        if key in header and str(header[key]).strip().upper() not in _EMPTY_FILTERS
    ]
    if len(used) != 1:
        raise HeaderError(f"expected exactly one filter in the wheels, found {used}")
    return used[0]


def pixel_scale_arcsec(header: Header) -> float:
    """Pixel scale from the WCS CD matrix, which already includes the binning."""
    try:
        cd11, cd12 = float(header["CD1_1"]), float(header["CD1_2"])
        cd21, cd22 = float(header["CD2_1"]), float(header["CD2_2"])
    except KeyError as error:
        raise HeaderError(f"missing WCS key {error}") from error
    determinant = abs(cd11 * cd22 - cd12 * cd21)
    if determinant == 0:
        raise HeaderError("singular CD matrix")
    return math.sqrt(determinant) * 3600.0


def _required(header: Header, key: str) -> str:
    if key not in header:
        raise HeaderError(f"missing key {key}")
    return str(header[key])


def _optional_float(header: Header, key: str) -> float | None:
    return float(header[key]) if key in header else None


def parse_header(header: Header) -> FrameHeader:
    binning = tuple(int(part) for part in _required(header, "CCDSUM").split())
    if len(binning) != 2:
        raise HeaderError(f"invalid CCDSUM {header['CCDSUM']!r}")
    return FrameHeader(
        filter=parse_filter(header),
        exptime_s=float(_required(header, "EXPTIME")),
        airmass=float(_required(header, "AIRMASS")),
        binning=(binning[0], binning[1]),
        pixel_scale_arcsec=pixel_scale_arcsec(header),
        gain_e_per_adu=float(_required(header, "GAIN")),
        read_noise_e=float(_required(header, "RDNOISE")),
        bias_section=parse_section(_required(header, "BIASSEC")),
        trim_section=parse_section(_required(header, "TRIMSEC")),
        date_obs=datetime.fromisoformat(_required(header, "DATE-OBS")),
        object=_required(header, "OBJECT").strip(),
        humidity_pct=_optional_float(header, "HUMIDITY"),
        wind_speed_ms=_optional_float(header, "WINDSPEE"),
        wind_dir_deg=_optional_float(header, "WINDDIRE"),
        pressure_hpa=_optional_float(header, "PRESSURE"),
        elevation_deg=_optional_float(header, "ELEVAT"),
        azimuth_deg=_optional_float(header, "AZIMUTH"),
        rotator_deg=_optional_float(header, "ROTANG"),
        focus=_optional_float(header, "AG1FOCUS"),
        ccd_temp_k=_optional_float(header, "CCDTEMP"),
    )
