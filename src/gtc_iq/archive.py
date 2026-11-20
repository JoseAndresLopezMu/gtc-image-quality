import csv
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ArchiveRow(BaseModel):
    """One product row from the CSV exported by the GTC public archive search form."""

    model_config = ConfigDict(frozen=True)

    product_id: int
    program_id: str
    block: str
    object: str
    instrument: str
    obs_mode: str
    start: datetime
    end: datetime
    exptime_s: float
    airmass: float | None
    raw_url: str | None
    reduced_url: str | None
    calib_url: str | None
    qc_url: str | None


class ArchiveCsvError(ValueError):
    pass


def _optional(value: str) -> str | None:
    return value or None


def read_archive_csv(path: Path) -> list[ArchiveRow]:
    # The archive writes ", " as separator and leaves empty fields blank.
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        if reader.fieldnames is None:
            raise ArchiveCsvError(f"{path}: empty file")
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        rows: list[ArchiveRow] = []
        for line_number, raw in enumerate(reader, start=2):
            fields = {key: (value or "").strip() for key, value in raw.items()}
            try:
                rows.append(
                    ArchiveRow(
                        product_id=int(fields["Prod ID"]),
                        program_id=fields["Program ID"],
                        block=fields["O.Block"],
                        object=fields["Object"],
                        instrument=fields["Instr."],
                        obs_mode=fields["Obs. Mode"],
                        start=datetime.fromisoformat(fields["Init.Time"]),
                        end=datetime.fromisoformat(fields["End Time"]),
                        exptime_s=float(fields["Exptime"]),
                        airmass=float(fields["Airmass"]) if fields["Airmass"] else None,
                        raw_url=_optional(fields["Raw Data"]),
                        reduced_url=_optional(fields["QLA Reduced Data"]),
                        calib_url=_optional(fields["Cal. Files"]),
                        qc_url=_optional(fields["QC Files"]),
                    )
                )
            except (KeyError, ValueError) as error:
                raise ArchiveCsvError(f"{path}:{line_number}: {error}") from error
    return rows


def select_block(rows: list[ArchiveRow], program_id: str, block: str) -> list[ArchiveRow]:
    selected = [row for row in rows if row.program_id == program_id and row.block == block]
    return sorted(selected, key=lambda row: row.start)
