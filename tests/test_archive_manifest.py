from datetime import datetime
from pathlib import Path

import pytest

from gtc_iq.archive import ArchiveCsvError, read_archive_csv, select_block
from gtc_iq.manifest import ManifestError, build_manifest, read_manifest, write_manifest

HEADER = (
    "Prod ID, Program ID, O.Block, Object, RA (deg), DEC (deg), RAJ2000, DECJ2000, Instr., "
    "Obs. Mode, Init.Time, End Time, Exptime, Airmass, Pub, User Reduced Data, "
    "GTC Reduced Data, QLA Reduced Data, Raw Data, Cal. Files, Acq. Images, QC Files"
)
# First data row of data/archive_query_2025A_osiris_bbi.csv, copied verbatim.
ROW_1 = (
    "5473717, GTC69-25B, 0001, WISE248, 327.86394, -5.54447, 21:51:27.35, -05:32:40.1, OSIRIS, "
    "BBI, 2025-07-29 02:21:05.0, 2025-07-29 02:24:05.0, 180, 1.21, 0, , , "
    "https://gtc.sdc.cab.inta-csic.es/gtc/FetchDataBlock?datablock=GTC69-25B__0001__5473717__ALLQLA, "
    "https://gtc.sdc.cab.inta-csic.es/gtc/servlet/FetchProd?prod_id=GTC69-25B..0001..5473717, "
    "https://gtc.sdc.cab.inta-csic.es/gtc/FetchDataBlock?datablock=GTC69-25B__0001__OSI__ALLCAL, , "
    "https://gtc.sdc.cab.inta-csic.es/gtc/FetchDataBlock?datablock=GTC69-25B__0001__OSI__ALLLOG"
)
ROW_2 = ROW_1.replace("5473717", "5473716").replace("02:21:05.0", "02:17:14.0")


def _write(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "archive.csv"
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def test_reads_real_row(tmp_path: Path) -> None:
    [row] = read_archive_csv(_write(tmp_path, ROW_1))
    assert row.product_id == 5473717
    assert row.block == "0001"
    assert row.start == datetime(2025, 7, 29, 2, 21, 5)
    assert row.exptime_s == 180
    assert row.airmass == 1.21
    assert row.raw_url is not None and row.raw_url.endswith("prod_id=GTC69-25B..0001..5473717")
    assert row.reduced_url is not None


def test_bad_row_reports_line(tmp_path: Path) -> None:
    with pytest.raises(ArchiveCsvError, match=":3:"):
        read_archive_csv(_write(tmp_path, ROW_1, ROW_1.replace("5473717,", "abc,", 1)))


def test_select_block_sorts_by_start(tmp_path: Path) -> None:
    rows = read_archive_csv(_write(tmp_path, ROW_1, ROW_2))
    selected = select_block(rows, "GTC69-25B", "0001")
    assert [row.product_id for row in selected] == [5473716, 5473717]
    assert select_block(rows, "GTC69-25B", "0002") == []


def test_manifest_round_trip(tmp_path: Path) -> None:
    entries = build_manifest(read_archive_csv(_write(tmp_path, ROW_1, ROW_2)))
    path = tmp_path / "manifest.csv"
    write_manifest(entries, path)
    assert read_manifest(path) == entries
    assert entries[0].filename == "raw_5473717.fits.gz"
    assert entries[0].sha256 is None


def test_manifest_requires_raw_url(tmp_path: Path) -> None:
    [row] = read_archive_csv(_write(tmp_path, ROW_1))
    with pytest.raises(ManifestError, match="5473717"):
        build_manifest([row.model_copy(update={"raw_url": None})])
