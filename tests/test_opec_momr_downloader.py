from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pipelines.opec_momr import downloader


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(downloader, "CACHE_DIR", tmp_path)


@pytest.mark.vcr
def test_download_appendix_caches_the_real_file() -> None:
    path = downloader.download_appendix(date(2026, 8, 1))

    assert path.exists()
    assert path.name == "momr-appendix-august-2026.xlsx"
    assert path.read_bytes()[:2] == b"PK"  # a real .xlsx (zip) file, not an error page

    # Second call is a cache hit -- no second request needed (would fail replay
    # under vcrpy's default record mode if it tried).
    cached_path = downloader.download_appendix(date(2026, 8, 15))
    assert cached_path == path


@pytest.mark.vcr
def test_download_appendix_raises_on_nonexistent_month() -> None:
    with pytest.raises(RuntimeError, match="unavailable"):
        downloader.download_appendix(date(2099, 12, 1))
