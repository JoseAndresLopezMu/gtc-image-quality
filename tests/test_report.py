from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from gtc_iq.analysis import FrameRecord
from gtc_iq.config import QCConfig
from gtc_iq.report import QCRow, Unmeasured, save_thumbnail, write_report

START = datetime(2025, 7, 20, 0, 30)


def _frames() -> list[FrameRecord]:
    frames: list[FrameRecord] = []
    for i in range(12):
        name = "Sloan_i" if i % 2 else "Sloan_z"
        airmass = 1.1 + 0.05 * i
        frames.append(
            FrameRecord(
                product_id=i,
                filter=name,
                date_obs=START + timedelta(minutes=3 * i),
                airmass=airmass,
                fwhm_arcsec=(1.0 if name == "Sloan_i" else 0.955) * airmass**0.6,
                ellipticity=0.05 + 0.01 * (i % 3),
                conditions={"wind_speed_ms": 7.0 + 0.1 * i, "focus": 12.0},
                passed=i != 5,
            )
        )
    return frames


def _qc(frames: list[FrameRecord]) -> dict[int, QCRow]:
    rows = {f.product_id: QCRow(f.product_id, True, "", "") for f in frames}
    rows[5] = QCRow(5, False, "high_ellipticity", "ellipticity 0.25 > 0.2: guiding")
    return rows


def _write(out: Path) -> Path:
    frames = _frames()
    return write_report(
        out,
        frames,
        [Unmeasured(99, "missing", "no file"), Unmeasured(98, "ok", "only 0 usable stars")],
        _qc(frames),
        QCConfig(),
        "qc:\n  max_ellipticity: 0.2\n",
        "abc123",
        "0.1.0",
    )


def test_report_has_every_section_and_figure(tmp_path: Path) -> None:
    text = _write(tmp_path).read_text(encoding="utf-8")
    for heading in (
        "## Datos",
        "## FWHM frente a masa de aire",
        "## Dependencia con la longitud de onda",
        "## Condiciones de la cabecera",
        "## Control de calidad",
        "## Tabla por fotograma",
        "## Configuración usada",
    ):
        assert heading in text
    for figure in ("fwhm_airmass.png", "fwhm_time.png", "fwhm_conditions.png", "ellipticity.png"):
        assert (tmp_path / figure).stat().st_size > 0
        assert f"({figure})" in text
    assert "`abc123`" in text
    assert "| 5 | high_ellipticity | ellipticity 0.25 > 0.2: guiding |" in text
    assert "- 99: missing, no file" in text
    assert "- 98: only 0 usable stars" in text
    assert "max_ellipticity: 0.2" in text
    # The flagged frame stays out of the fits: 6 Sloan_z and 5 Sloan_i.
    assert "| Sloan_i | todas juntas | 5 |" in text
    assert "| Sloan_z | todas juntas | 6 |" in text


def test_same_input_gives_identical_files(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    _write(first)
    _write(second)
    for path in sorted(first.iterdir()):
        assert path.read_bytes() == (second / path.name).read_bytes(), path.name


def test_thumbnail(tmp_path: Path) -> None:
    image = np.random.default_rng(0).normal(100, 5, (600, 400))
    save_thumbnail(image, "5: high_ellipticity", tmp_path / "thumb.png")
    assert (tmp_path / "thumb.png").read_bytes().startswith(b"\x89PNG")
