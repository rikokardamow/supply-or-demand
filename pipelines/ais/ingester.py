"""AIS ingester: aisstream.io websocket to hour-partitioned gzip JSONL (Spec 11, Session A).

Raw capture only. Nothing is parsed beyond the envelope, and nothing reaches the lake
here -- the compactor (Session C) turns these files into `vessel_positions` Parquet. Two
stages exist so that a slow disk can never slow the socket.

**Why a queue, and why it drops rather than blocks.** Spec 11's own note: aisstream drops
a client whose read queue backs up. If the reader awaited the writer, one slow flush would
stall the socket and cost the connection -- and a dropped connection loses *everything*
until the reconnect completes. A bounded queue that discards the newest message when full
loses a handful of positions instead. Both are losses; only one of them is bounded. The
drop count is logged on every heartbeat so it is never silent.

Reconnects are expected, not exceptional: the spec says so, and a terrestrial AIS network
behaves that way. Backoff is exponential with jitter, because a bare exponential has every
client in a region retrying in lockstep after a server-side blip.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import random
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol, TextIO

import websockets
from core.settings import settings

from pipelines.ais.geofences import subscription_boxes

STREAM_URL: Final = "wss://stream.aisstream.io/v0/stream"
RAW_ROOT: Final = Path("data/raw/ais")

# Only the two message types Spec 11 needs. Subscribing to everything multiplies volume
# for data the compactor would discard.
MESSAGE_TYPES: Final = ("PositionReport", "ShipStaticData")

# Roughly a minute of a busy stream. Large enough to absorb a slow flush, small enough
# that a genuinely stuck writer is visible as drops rather than unbounded memory.
QUEUE_SIZE: Final = 20_000

HEARTBEAT_SECONDS: Final = 60.0
MIN_BACKOFF_SECONDS: Final = 1.0
MAX_BACKOFF_SECONDS: Final = 60.0


class _Socket(Protocol):
    """The slice of a websocket connection this module uses."""

    async def send(self, message: str) -> None: ...
    def __aiter__(self) -> AsyncIterator[str | bytes]: ...


@dataclass
class Stats:
    """Counters for the heartbeat line. Reset per run, not per connection."""

    received: int = 0
    written: int = 0
    dropped: int = 0
    reconnects: int = 0
    started: datetime = field(default_factory=lambda: datetime.now(UTC))

    def line(self) -> str:
        elapsed = max((datetime.now(UTC) - self.started).total_seconds(), 1.0)
        return (
            f"ais: {self.received} received ({self.received / elapsed:.1f}/s), "
            f"{self.written} written, {self.dropped} dropped, "
            f"{self.reconnects} reconnects, {elapsed / 60:.1f} min"
        )


def subscription_message(api_key: str) -> str:
    """The subscribe frame aisstream expects as the first message after connecting."""
    return json.dumps(
        {
            "APIKey": api_key,
            "BoundingBoxes": subscription_boxes(),
            "FilterMessageTypes": list(MESSAGE_TYPES),
        }
    )


def raw_path(when: datetime, root: Path = RAW_ROOT) -> Path:
    """`data/raw/ais/YYYY/MM/DD/HH.jsonl.gz` -- hour-partitioned, per Spec 11.

    Hourly rather than daily so the compactor can process a closed hour while the current
    one is still being written, and so a crash costs at most one partial hour.
    """
    return root / f"{when:%Y}" / f"{when:%m}" / f"{when:%d}" / f"{when:%H}.jsonl.gz"


async def _writer(queue: asyncio.Queue[str], stats: Stats, root: Path) -> None:
    """Drain the queue to the current hour's file, reopening as the hour rolls over.

    Append mode, deliberately: a restart within the same hour must add to that hour's
    file rather than truncate what was already captured.
    """
    current_hour: str | None = None
    handle: TextIO | None = None

    try:
        while True:
            message = await queue.get()
            now = datetime.now(UTC)
            hour = f"{now:%Y%m%d%H}"

            if hour != current_hour:
                if handle is not None:
                    handle.close()
                path = raw_path(now, root)
                path.parent.mkdir(parents=True, exist_ok=True)
                # SIM115 suppressed: the handle deliberately outlives this block. It
                # stays open across messages and is closed on the hour rollover and in
                # the finally below; a context manager would reopen it per message.
                handle = gzip.open(path, "at", encoding="utf-8")  # noqa: SIM115
                current_hour = hour
                print(f"ais: writing to {path}", flush=True)

            assert handle is not None
            handle.write(message + "\n")
            stats.written += 1
            queue.task_done()
    except asyncio.CancelledError:
        raise
    finally:
        if handle is not None:
            handle.close()


async def _heartbeat(stats: Stats, queue: asyncio.Queue[str]) -> None:
    """One line a minute. A long silence from this is itself the signal."""
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        print(f"{stats.line()}, queue {queue.qsize()}", flush=True)


async def _consume(socket: _Socket, queue: asyncio.Queue[str], stats: Stats) -> None:
    """Read frames as fast as the socket delivers them; never await the disk here."""
    async for raw in socket:
        stats.received += 1
        message = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # Discard rather than block: see the module docstring. Counted, never silent.
            stats.dropped += 1


def _backoff(attempt: int) -> float:
    """Exponential with full jitter, capped.

    Full jitter rather than a fixed multiplier: after a server-side blip every client in
    a region would otherwise retry in lockstep and reproduce the overload that caused it.
    """
    ceiling = min(MAX_BACKOFF_SECONDS, MIN_BACKOFF_SECONDS * 2**attempt)
    return random.uniform(MIN_BACKOFF_SECONDS, ceiling)


async def run(
    *,
    minutes: float | None = None,
    root: Path = RAW_ROOT,
    connect: Any = None,
) -> Stats:
    """Capture until `minutes` elapses, or indefinitely when it is None.

    `connect` is injectable so the reconnect and drop behaviour can be tested without a
    network -- the real default is `websockets.connect`.
    """
    api_key = settings.aisstream_key
    if not api_key:
        raise RuntimeError("AISSTREAM_KEY is not set -- cannot subscribe to aisstream.io")

    connect = connect or websockets.connect
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
    stats = Stats()

    writer = asyncio.create_task(_writer(queue, stats, root))
    beat = asyncio.create_task(_heartbeat(stats, queue))
    deadline = None if minutes is None else asyncio.get_running_loop().time() + minutes * 60

    try:
        attempt = 0
        while deadline is None or asyncio.get_running_loop().time() < deadline:
            try:
                async with connect(STREAM_URL) as socket:
                    await socket.send(subscription_message(api_key))
                    print("ais: subscribed", flush=True)
                    attempt = 0  # a successful connect resets the backoff ladder
                    consume = asyncio.create_task(_consume(socket, queue, stats))
                    if deadline is None:
                        await consume
                    else:
                        remaining = deadline - asyncio.get_running_loop().time()
                        with suppress(TimeoutError):
                            await asyncio.wait_for(consume, timeout=max(remaining, 0.01))
                        if not consume.done():
                            consume.cancel()
                            with suppress(asyncio.CancelledError):
                                await consume
                            break
            except (TimeoutError, asyncio.CancelledError):
                raise
            except Exception as exc:
                stats.reconnects += 1
                delay = _backoff(attempt)
                attempt += 1
                print(f"ais: disconnected ({type(exc).__name__}), retrying in {delay:.1f}s",
                      flush=True)
                await asyncio.sleep(delay)
    finally:
        # Let the writer finish what is already queued before tearing it down, so a clean
        # shutdown does not discard captured messages.
        with suppress(TimeoutError):
            await asyncio.wait_for(queue.join(), timeout=10)
        for task in (writer, beat):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    print(stats.line(), flush=True)
    return stats


def main(minutes: float | None = None) -> None:
    asyncio.run(run(minutes=minutes))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--minutes",
        type=float,
        default=None,
        help="stop after this many minutes; omit to run until interrupted",
    )
    main(parser.parse_args().minutes)
