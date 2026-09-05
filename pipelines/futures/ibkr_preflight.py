"""Readiness check for the live IBKR futures path.

Run this *before* switching `FUTURES_SOURCE=ibkr` — it answers "is the Gateway actually
reachable, and is this project pointed at it?" without needing a Gateway to be running,
so it is safe to run any time and safe to unit-test.

    python -m pipelines.futures.ibkr_preflight

The historical clients are already built (`pipelines/futures/client.py`); what has never
existed is a way to confirm the live side is wired up. Every prior session recorded "all
four ports closed" by hand — this makes that check reproducible and puts the fix
instructions next to the result.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from typing import Any

from core.settings import settings

GATEWAY_PORTS = (7497, 7496, 4002, 4001)
"""TWS paper/live, then IB Gateway paper/live."""

PORT_LABELS = {
    7497: "TWS paper",
    7496: "TWS live",
    4002: "IB Gateway paper",
    4001: "IB Gateway live",
}

CONNECT_TIMEOUT = 1.0


def port_is_open(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> bool:
    """True if something accepts a TCP connection on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def preflight(
    port_open: Callable[[str, int], bool] = port_is_open,
    configured_host: str | None = None,
    configured_port: int | None = None,
) -> dict[str, Any]:
    """Probe every known Gateway port and report readiness.

    `port_open` is injected so this is testable without a live socket. A probe that
    raises is treated as "closed" rather than being allowed to abort the check — a
    readiness check that itself crashes is worse than useless.
    """
    host = configured_host if configured_host is not None else settings.ibkr_host
    port = configured_port if configured_port is not None else settings.ibkr_port

    open_ports = []
    for candidate in GATEWAY_PORTS:
        try:
            if port_open(host, candidate):
                open_ports.append(candidate)
        except OSError:
            continue

    ready = bool(open_ports)
    blocker = None
    if not ready:
        blocker = (
            "No IBKR Gateway or TWS is listening on this machine. Start IB Gateway "
            "(or TWS), log in, and enable API access under "
            "Configure > Settings > API > Enable ActiveX and Socket Clients."
        )

    return {
        "ready": ready,
        "open_ports": open_ports,
        "configured_host": host,
        "configured_port": port,
        "configured_port_open": port in open_ports,
        "futures_source": settings.futures_source,
        "blocker": blocker,
    }


def main() -> None:
    report = preflight()

    print("IBKR preflight")
    print(f"  configured : {report['configured_host']}:{report['configured_port']} "
          f"(FUTURES_SOURCE={report['futures_source']})")
    for port in GATEWAY_PORTS:
        state = "OPEN" if port in report["open_ports"] else "closed"
        print(f"  port {port} : {state:<6} ({PORT_LABELS[port]})")

    if not report["ready"]:
        print(f"\n  NOT READY -- {report['blocker']}")
        return

    print("\n  Gateway reachable.")
    if not report["configured_port_open"]:
        print(
            f"  WARNING: settings point at port {report['configured_port']}, which is "
            f"closed. Set IBKR_PORT to one of {report['open_ports']}."
        )
    if report["futures_source"] != "ibkr":
        print(
            f"  Next: set FUTURES_SOURCE=ibkr (currently {report['futures_source']!r}), "
            "then run `python -m pipelines.futures.pull_history`."
        )


if __name__ == "__main__":
    main()
