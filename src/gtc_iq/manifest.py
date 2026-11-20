import csv
import hashlib
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from gtc_iq.archive import ArchiveRow

FIELDS = ["product_id", "program_id", "block", "object", "start", "exptime_s", "url", "sha256"]


class ManifestEntry(BaseModel):
    product_id: int
    program_id: str
    block: str
    object: str
    start: datetime
    exptime_s: float
    url: str
    sha256: str | None = None

    @property
    def filename(self) -> str:
        return f"raw_{self.product_id}.fits.gz"


class ManifestError(ValueError):
    pass


def build_manifest(rows: list[ArchiveRow]) -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    for row in rows:
        if row.raw_url is None:
            raise ManifestError(f"product {row.product_id} has no raw data URL")
        entries.append(
            ManifestEntry(
                product_id=row.product_id,
                program_id=row.program_id,
                block=row.block,
                object=row.object,
                start=row.start,
                exptime_s=row.exptime_s,
                url=row.raw_url,
            )
        )
    return entries


def write_manifest(entries: list[ManifestEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for entry in entries:
            row = entry.model_dump(mode="json")
            row["sha256"] = row["sha256"] or ""
            writer.writerow(row)


def read_manifest(path: Path) -> list[ManifestEntry]:
    with path.open(newline="", encoding="utf-8") as handle:
        entries: list[ManifestEntry] = []
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                entries.append(
                    ManifestEntry.model_validate({**row, "sha256": row["sha256"] or None})
                )
            except (KeyError, ValueError) as error:
                raise ManifestError(f"{path}:{line_number}: {error}") from error
    return entries


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
