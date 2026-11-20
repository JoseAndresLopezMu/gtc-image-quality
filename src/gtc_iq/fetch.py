from collections.abc import Callable
from pathlib import Path

import httpx

from gtc_iq.manifest import ManifestEntry, sha256_of


class HashMismatchError(RuntimeError):
    pass


def fetch_entry(entry: ManifestEntry, data_dir: Path, client: httpx.Client) -> ManifestEntry:
    """Download one product unless a file with the expected hash is already there.

    Returns the entry with its hash filled in, so the first download freezes the manifest.
    """
    target = data_dir / entry.filename
    if target.exists() and entry.sha256 is not None and sha256_of(target) == entry.sha256:
        return entry

    partial = target.with_suffix(target.suffix + ".part")
    with client.stream("GET", entry.url) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)

    digest = sha256_of(partial)
    if entry.sha256 is not None and digest != entry.sha256:
        partial.unlink()
        raise HashMismatchError(
            f"product {entry.product_id}: expected {entry.sha256}, downloaded {digest}"
        )
    partial.replace(target)
    return entry.model_copy(update={"sha256": digest})


def fetch_all(
    entries: list[ManifestEntry],
    data_dir: Path,
    client: httpx.Client,
    on_done: Callable[[ManifestEntry], None] | None = None,
) -> list[ManifestEntry]:
    data_dir.mkdir(parents=True, exist_ok=True)
    updated: list[ManifestEntry] = []
    for entry in entries:
        done = fetch_entry(entry, data_dir, client)
        updated.append(done)
        if on_done is not None:
            on_done(done)
    return updated
