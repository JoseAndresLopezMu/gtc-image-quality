import numpy as np
import pytest
from astropy.io.fits import Header

from gtc_iq.headers import parse_header
from gtc_iq.preprocess import ADC_MAX, prepare_raw


def _raw_frame(bias: int, sky: int) -> np.ndarray:
    frame = np.full((2056, 2073), bias + sky, dtype=np.uint16)
    frame[:, 8:24] = bias  # BIASSEC [9:24, 1:2056]
    return frame


def test_subtracts_overscan_and_trims(raw_header: Header) -> None:
    header = parse_header(raw_header)
    prepared = prepare_raw(_raw_frame(bias=1000, sky=250), header)
    assert prepared.image.shape == (1797, 2033)
    assert prepared.bias_level_adu == 1000
    assert np.all(prepared.image == 250)


def test_flags_saturated_pixels_inside_trim(raw_header: Header) -> None:
    header = parse_header(raw_header)
    frame = _raw_frame(bias=1000, sky=250)
    frame[1000, 1000] = ADC_MAX  # inside TRIMSEC
    frame[10, 10] = ADC_MAX  # outside, in the overscan rows/columns
    prepared = prepare_raw(frame, header)
    assert prepared.saturated.sum() == 1
    assert prepared.saturated[1000 - 229, 1000 - 27]


def test_rejects_non_2d(raw_header: Header) -> None:
    with pytest.raises(ValueError, match="2D"):
        prepare_raw(np.zeros((2, 3, 4)), parse_header(raw_header))
