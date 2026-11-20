from datetime import datetime

import pytest
from astropy.io.fits import Header

from gtc_iq.headers import (
    HeaderError,
    parse_filter,
    parse_header,
    parse_section,
    pixel_scale_arcsec,
)


def test_parse_section_converts_fits_to_numpy() -> None:
    section = parse_section("[26:2073,1:2056]")
    assert (section.y0, section.y1, section.x0, section.x1) == (0, 2056, 25, 2073)


def test_trim_section_matches_adp_size() -> None:
    # The ADP of the same product is 2032 x 1796; TRIMSEC must give the same area +-1.
    section = parse_section("[28:2060,230:2026]")
    assert section.x1 - section.x0 == 2033
    assert section.y1 - section.y0 == 1797


@pytest.mark.parametrize("value", ["", "26:2073,1:2056", "[10:5,1:2]", "[a:b,c:d]"])
def test_parse_section_rejects_invalid(value: str) -> None:
    with pytest.raises(HeaderError):
        parse_section(value)


def test_parse_filter_ignores_open_wheels(raw_header: Header) -> None:
    assert parse_filter(raw_header) == "Sloan_i"


def test_parse_filter_rejects_two_filters(raw_header: Header) -> None:
    raw_header["FILTER1"] = "Sloan_r"
    with pytest.raises(HeaderError, match="exactly one filter"):
        parse_filter(raw_header)


def test_parse_filter_rejects_no_filter(raw_header: Header) -> None:
    raw_header["FILTER2"] = "OPEN"
    with pytest.raises(HeaderError):
        parse_filter(raw_header)


def test_pixel_scale_from_cd_matrix(raw_header: Header) -> None:
    assert pixel_scale_arcsec(raw_header) == pytest.approx(0.25436, abs=1e-4)


def test_pixel_scale_requires_cd(raw_header: Header) -> None:
    del raw_header["CD2_2"]
    with pytest.raises(HeaderError, match="CD2_2"):
        pixel_scale_arcsec(raw_header)


def test_parse_header_real_values(raw_header: Header) -> None:
    parsed = parse_header(raw_header)
    assert parsed.filter == "Sloan_i"
    assert parsed.binning == (2, 2)
    assert parsed.airmass == pytest.approx(1.468, abs=1e-3)
    assert parsed.wind_speed_ms == pytest.approx(7.70, abs=1e-2)
    assert parsed.date_obs == datetime(2025, 7, 20, 2, 22, 20, 10000)
    assert parsed.trim_section.slices == (slice(229, 2026), slice(27, 2060))


def test_parse_header_optional_keys_may_be_missing(raw_header: Header) -> None:
    del raw_header["HUMIDITY"]
    assert parse_header(raw_header).humidity_pct is None


@pytest.mark.parametrize("key", ["AIRMASS", "EXPTIME", "TRIMSEC", "BIASSEC", "CCDSUM"])
def test_parse_header_required_keys(raw_header: Header, key: str) -> None:
    del raw_header[key]
    with pytest.raises(HeaderError, match=key):
        parse_header(raw_header)
