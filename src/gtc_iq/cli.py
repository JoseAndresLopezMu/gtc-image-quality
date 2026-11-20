import csv
from pathlib import Path
from typing import Annotated

import httpx
import typer
from astropy.io import fits

from gtc_iq.archive import read_archive_csv, select_block
from gtc_iq.fetch import fetch_all
from gtc_iq.headers import HeaderError, parse_header
from gtc_iq.manifest import (
    ManifestEntry,
    build_manifest,
    read_manifest,
    sha256_of,
    write_manifest,
)

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
) -> None:
    """Build a manifest with the raw frames of one observing block."""
    rows = select_block(read_archive_csv(archive_csv), program, block)
    if not rows:
        raise typer.BadParameter(f"no products for {program} block {block}")
    write_manifest(build_manifest(rows), out)
    typer.echo(f"{len(rows)} products written to {out}")


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
