import csv
from datetime import datetime
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.io.fits import Header
from typer.testing import CliRunner

from gtc_iq.cli import app
from gtc_iq.manifest import ManifestEntry, sha256_of, write_manifest

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "manifest" in result.output


def _manifest(tmp_path: Path, ids: list[int]) -> Path:
    entries = [
        ManifestEntry(
            product_id=i,
            program_id="P",
            block="0001",
            object="X",
            start=datetime(2025, 7, 20),
            exptime_s=10,
            url=f"https://archive.test/{i}",
        )
        for i in ids
    ]
    path = tmp_path / "manifest.csv"
    write_manifest(entries, path)
    return path


def test_index_reports_each_status(tmp_path: Path, raw_header: Header) -> None:
    data = tmp_path / "raw"
    data.mkdir()
    image = np.zeros((4, 4), dtype=np.int16)
    fits.PrimaryHDU(image, header=raw_header).writeto(data / "raw_1.fits.gz")
    broken = raw_header.copy()
    del broken["AIRMASS"]
    fits.PrimaryHDU(image, header=broken).writeto(data / "raw_2.fits.gz")
    manifest = _manifest(tmp_path, [1, 2, 3])
    out = tmp_path / "index.csv"

    result = runner.invoke(
        app, ["index", "--manifest", str(manifest), "--data", str(data), "--out", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert "1/3 frames ok" in result.output
    rows = {row["product_id"]: row for row in csv.DictReader(out.open())}
    assert rows["1"]["status"] == "ok"
    assert rows["1"]["filter"] == "Sloan_i"
    assert rows["2"]["status"] == "unmeasurable"
    assert "AIRMASS" in rows["2"]["reason"]
    assert rows["3"]["status"] == "missing"
    assert sha256_of(data / "raw_1.fits.gz")
