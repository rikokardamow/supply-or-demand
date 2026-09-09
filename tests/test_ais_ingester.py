from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pipelines.ais import ingester
from pipelines.ais.ingester import Stats, raw_path, run, subscription_message


class _FakeSocket:
    """A websocket that yields a fixed set of frames, then optionally raises."""

    def __init__(self, frames: list[str], then_raise: Exception | None = None) -> None:
        self.frames = frames
        self.then_raise = then_raise
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def __aiter__(self) -> AsyncIterator[str]:  # type: ignore[override]
        for frame in self.frames:
            yield frame
        if self.then_raise is not None:
            raise self.then_raise
        # Idle rather than returning: a real socket stays open with no traffic, and the
        # run loop must be stopped by its deadline, not by the stream ending.
        await asyncio.sleep(3600)


class _FakeConnect:
    """Stands in for `websockets.connect`, handing out sockets in order."""

    def __init__(self, sockets: list[_FakeSocket]) -> None:
        self.sockets = sockets
        self.calls = 0

    def __call__(self, url: str) -> _FakeConnect:
        self.url = url
        return self

    async def __aenter__(self) -> _FakeSocket:
        socket = self.sockets[min(self.calls, len(self.sockets) - 1)]
        self.calls += 1
        return socket

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipelines.ais.ingester.settings.aisstream_key", "test-key")


def test_subscription_message_has_the_shape_aisstream_expects() -> None:
    payload = json.loads(subscription_message("k"))

    assert payload["APIKey"] == "k"
    assert payload["FilterMessageTypes"] == ["PositionReport", "ShipStaticData"]
    # Latitude first, and every box a pair of corners -- aisstream accepts a transposed
    # box and then silently yields nothing.
    for box in payload["BoundingBoxes"]:
        (south, west), (north, east) = box
        assert south < north
        assert west < east


def test_raw_path_is_hour_partitioned() -> None:
    got = raw_path(datetime(2026, 9, 9, 14, 30, tzinfo=UTC), root=Path("/tmp/ais"))

    assert got == Path("/tmp/ais/2026/09/09/14.jsonl.gz")


def test_run_writes_every_received_frame_to_the_hour_file(tmp_path: Path) -> None:
    frames = [json.dumps({"MessageType": "PositionReport", "n": i}) for i in range(5)]
    connect = _FakeConnect([_FakeSocket(frames)])

    stats = asyncio.run(run(minutes=0.02, root=tmp_path, connect=connect))

    assert stats.received == 5
    assert stats.written == 5
    written = list(tmp_path.rglob("*.jsonl.gz"))
    assert len(written) == 1
    with gzip.open(written[0], "rt", encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle]
    assert [line["n"] for line in lines] == [0, 1, 2, 3, 4]


def test_run_subscribes_before_reading(tmp_path: Path) -> None:
    socket = _FakeSocket([])
    connect = _FakeConnect([socket])

    asyncio.run(run(minutes=0.02, root=tmp_path, connect=connect))

    assert len(socket.sent) == 1
    assert json.loads(socket.sent[0])["APIKey"] == "test-key"


def test_run_reconnects_after_a_dropped_connection(tmp_path: Path) -> None:
    # Spec 11 treats disconnects as normal, not exceptional: a terrestrial AIS feed drops
    # clients routinely, and a run that gave up on the first one would capture minutes
    # rather than days.
    first = _FakeSocket([json.dumps({"n": 1})], then_raise=ConnectionResetError("dropped"))
    second = _FakeSocket([json.dumps({"n": 2})])
    connect = _FakeConnect([first, second])

    stats = asyncio.run(run(minutes=0.05, root=tmp_path, connect=connect))

    assert stats.reconnects >= 1
    assert connect.calls >= 2
    assert stats.received >= 2


def test_a_full_queue_drops_messages_rather_than_blocking_the_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The central design decision. aisstream disconnects a client whose read queue backs
    # up, and a dropped connection loses everything until reconnect; a bounded queue that
    # discards loses a handful of positions. Both lose data, only one loss is bounded.
    monkeypatch.setattr(ingester, "QUEUE_SIZE", 2)

    async def _never_drain(*_a: Any, **_k: Any) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(ingester, "_writer", _never_drain)

    frames = [json.dumps({"n": i}) for i in range(50)]
    connect = _FakeConnect([_FakeSocket(frames)])

    stats = asyncio.run(run(minutes=0.02, root=tmp_path, connect=connect))

    assert stats.received == 50
    assert stats.dropped > 0, "a stalled writer must cause drops, never a blocked socket"
    assert stats.written == 0


def test_run_refuses_to_start_without_an_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pipelines.ais.ingester.settings.aisstream_key", None)

    with pytest.raises(RuntimeError, match="AISSTREAM_KEY"):
        asyncio.run(run(minutes=0.01, root=tmp_path, connect=_FakeConnect([_FakeSocket([])])))


def test_stats_line_reports_the_counters_a_heartbeat_needs() -> None:
    stats = Stats(received=10, written=8, dropped=2, reconnects=1)

    line = stats.line()

    assert "10 received" in line
    assert "8 written" in line
    assert "2 dropped" in line
    assert "1 reconnects" in line
