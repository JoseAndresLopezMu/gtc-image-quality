import hashlib
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from gtc_iq.fetch import HashMismatchError, fetch_all, fetch_entry
from gtc_iq.manifest import ManifestEntry

PAYLOAD = b"fake fits content"


def _entry(sha256: str | None = None) -> ManifestEntry:
    return ManifestEntry(
        product_id=1,
        program_id="P",
        block="0001",
        object="X",
        start=datetime(2025, 7, 20),
        exptime_s=10,
        url="https://archive.test/raw/1",
        sha256=sha256,
    )


def _client(calls: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=PAYLOAD)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_first_download_freezes_hash(tmp_path: Path) -> None:
    calls: list[str] = []
    [done] = fetch_all([_entry()], tmp_path, _client(calls))
    assert done.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert (tmp_path / "raw_1.fits.gz").read_bytes() == PAYLOAD
    assert calls == ["https://archive.test/raw/1"]


def test_skips_file_with_matching_hash(tmp_path: Path) -> None:
    (tmp_path / "raw_1.fits.gz").write_bytes(PAYLOAD)
    calls: list[str] = []
    fetch_entry(_entry(hashlib.sha256(PAYLOAD).hexdigest()), tmp_path, _client(calls))
    assert calls == []


def test_hash_mismatch_leaves_no_file(tmp_path: Path) -> None:
    with pytest.raises(HashMismatchError, match="product 1"):
        fetch_entry(_entry("0" * 64), tmp_path, _client([]))
    assert list(tmp_path.iterdir()) == []


def test_http_error_raises(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404)))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_entry(_entry(), tmp_path, client)
