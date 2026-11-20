from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from gtc_iq.headers import FrameHeader

# OSIRIS+ raw frames are unsigned 16-bit, so the converter tops out at this value.
ADC_MAX = 65535


@dataclass(frozen=True)
class PreparedFrame:
    image: NDArray[np.float64]
    saturated: NDArray[np.bool_]
    bias_level_adu: float


def prepare_raw(data: NDArray[np.generic], header: FrameHeader) -> PreparedFrame:
    """Overscan subtraction and trimming of a raw frame (SPEC 5.0)."""
    if data.ndim != 2:
        raise ValueError(f"expected a 2D image, got shape {data.shape}")
    pixels = np.asarray(data, dtype=np.float64)
    saturated = pixels >= ADC_MAX
    bias_level = float(np.median(pixels[header.bias_section.slices]))
    trim = header.trim_section.slices
    return PreparedFrame(
        image=pixels[trim] - bias_level,
        saturated=saturated[trim],
        bias_level_adu=bias_level,
    )
