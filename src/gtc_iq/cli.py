import csv
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import httpx
import typer
from astropy.io import fits

from gtc_iq.archive import read_archive_csv, select_block
from gtc_iq.config import load_config
from gtc_iq.fetch import fetch_all
from gtc_iq.headers import HeaderError, parse_header
from gtc_iq.manifest import (
    ManifestEntry,
    build_manifest,
    read_manifest,
    sha256_of,
    write_manifest,
)
from gtc_iq.measure import measure_frame
from gtc_iq.preprocess import prepare_raw
from gtc_iq.qc import FrameQCInput, apply_rules
from gtc_iq.report import read_qc, read_records, save_thumbnail, write_report

app = typer.Typer(help="Measure image quality of GTC OSIRIS+ frames.", no_args_is_help=True)

INDEX_FIELDS = [
    "product_id",
    "status",
    "reason",
    "filter",
    "exptime_s",
    "airmass",
    "pixel_scale_arcsec",
    "humidity_pct",
    "wind_speed_ms",
    "wind_dir_deg",
    "elevation_deg",
    "focus",
    "date_obs",
]


@app.command()
def manifest(
    archive_csv: Annotated[Path, typer.Option(help="CSV exported by the archive search form")],
    program: Annotated[str, typer.Option(help="Program ID, e.g. GTCMULTIPLE7B-25A")],
    block: Annotated[str, typer.Option(help="Observing block, e.g. 0037")],
    out: Annotated[Path, typer.Option(help="Manifest CSV to write")],
    append: Annotated[
        bool, typer.Option(help="Add the block to an existing manifest, keeping its hashes")
    ] = False,
) -> None:
    """Build a manifest with the raw frames of one observing block."""
    rows = select_block(read_archive_csv(archive_csv), program, block)
    if not rows:
        raise typer.BadParameter(f"no products for {program} block {block}")
    entries = build_manifest(rows)
    if append and out.exists():
        existing = read_manifest(out)
        known = {entry.product_id for entry in existing}
        entries = existing + [entry for entry in entries if entry.product_id not in known]
    write_manifest(entries, out)
    typer.echo(f"{len(rows)} products of block {block}, {len(entries)} in {out}")


@app.command()
def fetch(
    manifest: Annotated[Path, typer.Option(help="Manifest CSV")],
    data: Annotated[Path, typer.Option(help="Directory for the raw frames")],
) -> None:
    """Download the manifest products and freeze their SHA-256 in the manifest."""
    entries = read_manifest(manifest)

    def report(entry: ManifestEntry) -> None:
        typer.echo(f"ok {entry.product_id}")

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        updated = fetch_all(entries, data, client, on_done=report)
    write_manifest(updated, manifest)


@app.command()
def index(
    manifest: Annotated[Path, typer.Option(help="Manifest CSV")],
    data: Annotated[Path, typer.Option(help="Directory with the raw frames")],
    out: Annotated[Path, typer.Option(help="Index CSV to write")],
) -> None:
    """Check files against the manifest and read the header of every frame."""
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for entry in read_manifest(manifest):
        path = data / entry.filename
        row: dict[str, object] = {"product_id": entry.product_id}
        if not path.exists():
            row |= {"status": "missing", "reason": f"{path} not found"}
        elif entry.sha256 is not None and sha256_of(path) != entry.sha256:
            row |= {"status": "corrupt", "reason": "hash differs from manifest"}
        else:
            try:
                parsed = parse_header(fits.getheader(path))
            except HeaderError as error:
                row |= {"status": "unmeasurable", "reason": str(error)}
            else:
                row |= {"status": "ok", "reason": ""}
                row |= parsed.model_dump(include=set(INDEX_FIELDS))
        rows.append(row)

    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    ok = sum(1 for row in rows if row["status"] == "ok")
    typer.echo(f"{ok}/{len(rows)} frames ok, index written to {out}")


FRAME_FIELDS = [
    *INDEX_FIELDS,
    "n_detected",
    "n_used",
    "n_edge",
    "n_saturated",
    "n_crowded",
    "n_not_compact",
    "n_fit_failed",
    "fwhm_px",
    "fwhm_mad_px",
    "fwhm_arcsec",
    "fwhm_gauss_px",
    "ellipticity",
    "ellipticity_moments",
    "background_adu",
    "background_noise_adu",
    "saturated_fraction",
    "bias_level_adu",
]
STAR_FIELDS = [
    "product_id",
    "x",
    "y",
    "fwhm_px",
    "fwhm_major_px",
    "fwhm_minor_px",
    "fwhm_gauss_px",
    "ellipticity_fit",
    "ellipticity_moments",
    "theta_rad",
    "beta",
]
QC_FIELDS = ["product_id", "passed", "flags", "reasons"]


def _measure_one(path: Path, product_id: int) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Measure one raw frame. Runs in a worker process, so it only returns plain data."""
    row: dict[str, object] = {"product_id": product_id}
    with fits.open(path) as hdul:
        data, header = hdul[0].data, hdul[0].header
    try:
        parsed = parse_header(header)
    except HeaderError as error:
        return row | {"status": "unmeasurable", "reason": str(error)}, []
    prepared = prepare_raw(data, parsed)
    result = measure_frame(prepared.image, prepared.saturated, parsed.pixel_scale_arcsec)
    row |= parsed.model_dump(include=set(INDEX_FIELDS))
    row |= {"n_" + reason: count for reason, count in result.rejected.items()}
    row |= {
        key: value
        for key, value in asdict(result).items()
        if key not in {"rejected", "stars"} and key in FRAME_FIELDS
    }
    row |= {"bias_level_adu": prepared.bias_level_adu}
    if result.fwhm_px is None:
        row |= {"status": "ok", "reason": f"only {result.n_used} usable stars"}
    else:
        row |= {"status": "ok", "reason": ""}
    stars = [{"product_id": product_id, **asdict(star)} for star in result.stars]
    return row, stars


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


@app.command()
def measure(
    manifest: Annotated[Path, typer.Option(help="Manifest CSV")],
    data: Annotated[Path, typer.Option(help="Directory with the raw frames")],
    out: Annotated[Path, typer.Option(help="Per-frame CSV to write")],
    stars: Annotated[Path | None, typer.Option(help="Optional per-star CSV")] = None,
    jobs: Annotated[int, typer.Option(help="Frames measured in parallel")] = 1,
) -> None:
    """Measure FWHM, ellipticity, background and saturation of every frame (SPEC 5)."""
    entries = read_manifest(manifest)
    rows: list[dict[str, object]] = []
    star_rows: list[dict[str, object]] = []
    to_measure: list[tuple[Path, int]] = []
    for entry in entries:
        path = data / entry.filename
        if not path.exists():
            rows.append({"product_id": entry.product_id, "status": "missing", "reason": "no file"})
        elif entry.sha256 is not None and sha256_of(path) != entry.sha256:
            rows.append(
                {"product_id": entry.product_id, "status": "corrupt", "reason": "hash differs"}
            )
        else:
            to_measure.append((path, entry.product_id))

    paths = [path for path, _ in to_measure]
    ids = [product_id for _, product_id in to_measure]
    if jobs > 1:
        with ProcessPoolExecutor(min(jobs, os.cpu_count() or 1)) as pool:
            results = list(pool.map(_measure_one, paths, ids))
    else:
        results = [_measure_one(path, product_id) for path, product_id in to_measure]
    for row, frame_stars in results:
        rows.append(row)
        star_rows.extend(frame_stars)
        typer.echo(f"{row['product_id']} {row['status']} {row.get('fwhm_arcsec', '')}")

    rows.sort(key=lambda row: int(str(row["product_id"])))
    _write_csv(out, FRAME_FIELDS, rows)
    if stars is not None:
        _write_csv(stars, STAR_FIELDS, star_rows)
    measured = sum(1 for row in rows if row.get("fwhm_px") is not None)
    typer.echo(f"{measured}/{len(rows)} frames measured, written to {out}")


def _optional(value: str) -> float | None:
    return float(value) if value else None


def read_frames(path: Path) -> list[FrameQCInput]:
    frames: list[FrameQCInput] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            status = row["status"]
            frames.append(
                FrameQCInput(
                    product_id=int(row["product_id"]),
                    status="ok" if status == "ok" else "unmeasurable",
                    reason=row["reason"] or ("" if status == "ok" else status),
                    filter=row["filter"] or None,
                    date_obs=datetime.fromisoformat(row["date_obs"]) if row["date_obs"] else None,
                    exptime_s=_optional(row["exptime_s"]),
                    n_used=int(row["n_used"] or 0),
                    fwhm_arcsec=_optional(row["fwhm_arcsec"]),
                    ellipticity=_optional(row["ellipticity"]),
                    background_adu=_optional(row["background_adu"]),
                    saturated_fraction=_optional(row["saturated_fraction"]),
                )
            )
    return frames


@app.command()
def qc(
    frames: Annotated[Path, typer.Option(help="Per-frame CSV written by measure")],
    config: Annotated[Path, typer.Option(help="YAML with the qc thresholds")],
    out: Annotated[Path, typer.Option(help="QC CSV to write")],
) -> None:
    """Flag doubtful frames, each flag with its reason (SPEC 6)."""
    results = apply_rules(read_frames(frames), load_config(config))
    rows: list[dict[str, object]] = [
        {
            "product_id": r.product_id,
            "passed": r.passed,
            "flags": ";".join(flag.rule for flag in r.flags),
            "reasons": " | ".join(flag.reason for flag in r.flags),
        }
        for r in results
    ]
    _write_csv(out, QC_FIELDS, rows)
    flagged = [r for r in results if not r.passed]
    for r in flagged:
        for flag in r.flags:
            typer.echo(f"{r.product_id} {flag.rule}: {flag.reason}")
    typer.echo(f"{len(flagged)}/{len(results)} frames flagged, written to {out}")


@app.command()
def report(
    frames: Annotated[Path, typer.Option(help="Per-frame CSV written by measure")],
    qc: Annotated[Path, typer.Option(help="QC CSV written by qc")],
    config: Annotated[Path, typer.Option(help="YAML used by qc, copied into the report")],
    manifest: Annotated[Path, typer.Option(help="Manifest CSV, whose hash goes in the report")],
    out: Annotated[Path, typer.Option(help="Directory for report.md and the figures")],
    data: Annotated[
        Path | None, typer.Option(help="Raw frames, for thumbnails of the flagged frames")
    ] = None,
) -> None:
    """Write the Markdown report with the airmass and wavelength analysis (SPEC 5.5 and 8)."""
    qc_rows = read_qc(qc)
    records, unmeasured = read_records(frames, qc_rows)
    out.mkdir(parents=True, exist_ok=True)
    thumbnails: dict[int, Path] = {}
    if data is not None:
        for row in qc_rows.values():
            path = data / f"raw_{row.product_id}.fits.gz"
            if row.passed or not path.exists():
                continue
            with fits.open(path) as hdul:
                raw, header = hdul[0].data, hdul[0].header
            try:
                prepared = prepare_raw(raw, parse_header(header))
            except HeaderError:
                continue
            thumbnails[row.product_id] = out / f"thumb_{row.product_id}.png"
            save_thumbnail(
                prepared.image, f"{row.product_id}: {row.flags}", thumbnails[row.product_id]
            )
    path = write_report(
        out,
        records,
        unmeasured,
        qc_rows,
        load_config(config),
        config.read_text(encoding="utf-8"),
        sha256_of(manifest),
        version("gtc-image-quality"),
        thumbnails,
    )
    typer.echo(f"{len(records)} frames in the report, written to {path}")
