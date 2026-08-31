from __future__ import annotations

from pathlib import Path

import pytest
from pipelines.baker_hughes import client

_SAMPLE_HTML = """
<html><body>
<p>Rig Count Methodology Change -
<a href="/static-files/methodology-uuid">Read More</a></p>
<span><a href="/static-files/current-report-uuid">
North America Rig Count Report - New Report</a></span>
<span><a href="/static-files/archive-uuid">
North America Rig Count New Report (2013-Aug 2025)</a></span>
</body></html>
"""


class _FakeResponse:
    def __init__(self, content: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.content = content
        self.text = content.decode()
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)


def test_find_current_report_url_picks_the_new_report_not_the_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, timeout: int) -> _FakeResponse:
        return _FakeResponse(_SAMPLE_HTML.encode())

    monkeypatch.setattr(client.requests, "get", fake_get)

    url = client.find_current_report_url()

    assert url == "https://rigcount.bakerhughes.com/static-files/current-report-uuid"


def test_find_current_report_url_raises_if_label_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, timeout: int) -> _FakeResponse:
        return _FakeResponse(b"<html><body>no relevant links here</body></html>")

    monkeypatch.setattr(client.requests, "get", fake_get)

    with pytest.raises(ValueError, match="Could not find a link labelled"):
        client.find_current_report_url()


def test_download_current_report_reads_date_from_content_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, timeout: int) -> _FakeResponse:
        if "na-rig-count" in url:
            return _FakeResponse(_SAMPLE_HTML.encode())
        return _FakeResponse(
            b"fake xlsx bytes",
            headers={"Content-Disposition": 'attachment; filename="08-28-2026 Report.xlsx"'},
        )

    def fake_head(url: str, timeout: int, allow_redirects: bool) -> _FakeResponse:
        return _FakeResponse(
            headers={"Content-Disposition": 'attachment; filename="08-28-2026 Report.xlsx"'}
        )

    monkeypatch.setattr(client.requests, "get", fake_get)
    monkeypatch.setattr(client.requests, "head", fake_head)

    path, report_date = client.download_current_report()

    assert report_date == "2026-08-28"
    assert path.name == "rig-count-2026-08-28.xlsx"
    assert path.read_bytes() == b"fake xlsx bytes"


def test_download_current_report_skips_the_full_get_on_a_cache_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cached = tmp_path / "rig-count-2026-08-28.xlsx"
    cached.write_bytes(b"already cached")
    get_calls: list[str] = []

    def fake_get(url: str, timeout: int) -> _FakeResponse:
        get_calls.append(url)
        return _FakeResponse(_SAMPLE_HTML.encode())  # only the landing page should be GET'd

    def fake_head(url: str, timeout: int, allow_redirects: bool) -> _FakeResponse:
        return _FakeResponse(
            headers={"Content-Disposition": 'attachment; filename="08-28-2026 Report.xlsx"'}
        )

    monkeypatch.setattr(client.requests, "get", fake_get)
    monkeypatch.setattr(client.requests, "head", fake_head)

    path, report_date = client.download_current_report()

    assert report_date == "2026-08-28"
    assert path.read_bytes() == b"already cached"
    # Only the landing-page GET happened -- no GET for the (large) xlsx itself.
    assert len(get_calls) == 1
