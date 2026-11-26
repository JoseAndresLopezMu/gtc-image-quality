import csv
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.io.fits import Header
from typer.testing import CliRunner

from gtc_iq.cli import app
from gtc_iq.manifest import ManifestEntry, sha256_of, write_manifest
from gtc_iq.synthetic import StarSpec, make_frame

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


def _raw_frame(path: Path, header: Header, airmass: float, seed: int) -> None:
    # Small raw frame: 10 overscan columns, then a 300 x 300 sky with a grid of stars.
    stars = [StarSpec(40 + 55 * (i % 5), 40 + 55 * (i // 5), 2e5, 4.0, 0.1, 0.4) for i in range(25)]
    sky = make_frame((300, 300), stars, seed=seed)
    image = np.full((300, 310), 300.0)
    image[:, 10:] += sky
    header = header.copy()
    header["BIASSEC"] = "[1:10,1:300]"
    header["TRIMSEC"] = "[11:310,1:300]"
    header["AIRMASS"] = airmass
    fits.PrimaryHDU(np.clip(image, 0, 65535).astype(np.uint16), header=header).writeto(path)


def test_measure_then_qc(tmp_path: Path, raw_header: Header) -> None:
    data = tmp_path / "raw"
    data.mkdir()
    for i in (1, 2):
        _raw_frame(data / f"raw_{i}.fits.gz", raw_header, airmass=1.2 + 0.1 * i, seed=i)
    manifest = _manifest(tmp_path, [1, 2, 3])
    frames, stars, qc_out = tmp_path / "frames.csv", tmp_path / "stars.csv", tmp_path / "qc.csv"

    args = ["--manifest", str(manifest), "--data", str(data), "--out", str(frames)]
    result = runner.invoke(app, ["measure", *args, "--stars", str(stars)])

    assert result.exit_code == 0, result.output
    rows = {row["product_id"]: row for row in csv.DictReader(frames.open())}
    assert rows["1"]["status"] == "ok"
    assert rows["1"]["filter"] == "Sloan_i"
    assert int(rows["1"]["n_used"]) == 25
    assert float(rows["1"]["fwhm_px"]) == pytest.approx(4.0 * 0.9**0.5, rel=0.05)
    assert float(rows["2"]["airmass"]) == pytest.approx(1.4)
    assert rows["3"]["status"] == "missing"
    assert len(list(csv.DictReader(stars.open()))) == 50

    config = tmp_path / "config.yaml"
    config.write_text("qc:\n  max_ellipticity: 0.05\n", encoding="utf-8")
    result = runner.invoke(
        app, ["qc", "--frames", str(frames), "--config", str(config), "--out", str(qc_out)]
    )

    assert result.exit_code == 0, result.output
    qc_rows = {row["product_id"]: row for row in csv.DictReader(qc_out.open())}
    assert qc_rows["1"]["flags"] == "high_ellipticity"
    assert "0.05" in qc_rows["1"]["reasons"]
    assert qc_rows["3"]["flags"] == "unmeasurable"
    assert "3/3 frames flagged" in result.output


def test_report_after_qc(tmp_path: Path, raw_header: Header) -> None:
    data = tmp_path / "raw"
    data.mkdir()
    for i in (1, 2):
        _raw_frame(data / f"raw_{i}.fits.gz", raw_header, airmass=1.2 + 0.1 * i, seed=i)
    manifest = _manifest(tmp_path, [1, 2])
    frames, qc_out, out = tmp_path / "frames.csv", tmp_path / "qc.csv", tmp_path / "report"
    config = tmp_path / "config.yaml"
    config.write_text("qc:\n  max_ellipticity: 0.05\n", encoding="utf-8")
    args = ["--manifest", str(manifest), "--data", str(data)]
    assert runner.invoke(app, ["measure", *args, "--out", str(frames)]).exit_code == 0
    qc_args = ["--frames", str(frames), "--config", str(config), "--out", str(qc_out)]
    assert runner.invoke(app, ["qc", *qc_args]).exit_code == 0

    report_args = ["--frames", str(frames), "--qc", str(qc_out), "--config", str(config)]
    result = runner.invoke(app, ["report", *report_args, *args, "--out", str(out)])

    assert result.exit_code == 0, result.output
    text = (out / "report.md").read_text(encoding="utf-8")
    assert sha256_of(manifest) in text
    assert "max_ellipticity: 0.05" in text
    assert "| 1 | high_ellipticity |" in text
    assert (out / "thumb_1.png").exists()
    assert "(thumb_1.png)" in text
