import pytest
from astropy.io.fits import Header

# Values copied from the raw header of product 5456875 (GTCMULTIPLE7B-25A, block 0037).
REAL_RAW_CARDS: dict[str, object] = {
    "NAXIS1": 2073,
    "NAXIS2": 2056,
    "CCDSUM": "2 2",
    "DATASEC": "[26:2073,1:2056]",
    "BIASSEC": "[9:24,1:2056]",
    "TRIMSEC": "[28:2060,230:2026]",
    "DATE-OBS": "2025-07-20T02:22:20.010",
    "GAIN": 1.9,
    "RDNOISE": 4.3,
    "EXPTIME": 100.0,
    "AG1FOCUS": 12.12052734375,
    "ROTANG": -90.6341666666667,
    "HUMIDITY": 5.6,
    "WINDSPEE": 7.69597777777831,
    "WINDDIRE": 53.9,
    "AIRMASS": 1.46795393621249,
    "CCDTEMP": 160.009994506836,
    "FILTER4": "OPEN",
    "FILTER1": "OPEN",
    "FILTER2": "Sloan_i",
    "FILTER3": "OPEN",
    "CD1_1": 7.06555555555555e-05,
    "CD1_2": 9.58626715136134e-19,
    "OBJECT": "GRB250702B-E",
    "PRESSURE": 780.2819,
    "AZIMUTH": -134.916817197898,
    "ELEVAT": 42.8814993840598,
}


@pytest.fixture
def raw_header() -> Header:
    header = Header()
    for key, value in REAL_RAW_CARDS.items():
        header[key] = value
    header["CD2_1"] = -9.58626715136134e-19
    header["CD2_2"] = 7.06555555555555e-05
    return header
