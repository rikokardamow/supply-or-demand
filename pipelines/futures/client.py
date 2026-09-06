"""Futures/options settlements -- two interchangeable clients behind one interface,
selected by `settings.futures_source` ("ibkr" or "manual"). See CLAUDE.md for the real,
confirmed-live finding that drove this session's choice of "manual" (no IBKR Gateway/TWS
is running on this machine) and why `ib_async` (not `ib_insync`) is the dependency."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol

import pandas as pd
from core.failures import record_failure
from core.settings import settings

ROOTS = ("cl", "rb", "ho", "ng", "lco", "g", "tfm")

CONTRACT_SPECS_PATH = Path(__file__).parent / "contract_specs.csv"
MANUAL_FUTURES_DIR = Path("data/manual/futures")

_SETTLES_COLUMNS = ["date", "root", "contract", "settle", "oi", "volume", "expiry"]


@dataclass(frozen=True)
class ContractMeta:
    root: str
    contract: str  # lowercase, e.g. "z26" (month code + 2-digit year)
    expiry: date
    tick_size: float
    contract_unit: str
    currency: str


class FuturesClient(Protocol):
    def list_contracts(self, root: str) -> list[ContractMeta]: ...

    def get_settles(
        self, root: str, contracts: list[str], start: date, end: date
    ) -> pd.DataFrame:
        """Returns columns: date, root, contract, settle, oi, volume."""
        ...


def load_contract_specs(path: Path = CONTRACT_SPECS_PATH) -> pd.DataFrame:
    """Static per-root tick_size/contract_unit/currency -- well-documented public CME/ICE
    contract specifications (confirm against the exchange's own current contract-spec page
    before relying on these for a real trading calculation; they are not fetched live from
    anywhere, same precedent as pipelines/opec_momr/quotas.csv)."""
    return pd.read_csv(path)


RANK_CODE_PATTERN = re.compile(r"f(0[1-9]|[12][0-9]|3[0-6])")
"""The conventions' nearby-rank namespace: `fut.<root>.f01.settle` ... `f36`."""


def looks_like_rank_code(contract: str) -> bool:
    """True if a *contract* code is indistinguishable from a nearby rank.

    January's exchange month letter is "F", so a Jan-2027 contract written with a
    two-digit year (`f27`) collides with rank 27. Eight such series were live in the lake
    before this was caught. Four-digit years (`f2027`) cannot collide, and are what
    `pipelines/futures/barchart_curve.py` now emits -- anything reaching the lake from an
    operator CSV or IBKR must clear this guard too.
    """
    return RANK_CODE_PATTERN.fullmatch(contract.strip().lower()) is not None


IB_MAX_DAYS_PER_REQUEST = 365
"""IB's historical API caps how much a single daily-bar request may span. pull_history's
own multi-decade backfill therefore has to be chunked -- a 1993-present `durationStr`
is rejected outright, which is the first thing a real Gateway run would have hit."""


def duration_windows(
    start: date, end: date, max_days: int = IB_MAX_DAYS_PER_REQUEST
) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive windows no longer than `max_days`.

    Windows share their boundary date (each starts where the previous ended) rather than
    leaving a one-day gap -- the duplicate bar is removed by the lake's own
    (series_id, ts) de-dup on write, whereas a gap would silently lose a settlement.
    """
    if end < start:
        raise ValueError("end must not be before start")

    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(days=max_days), end)
        windows.append((cursor, stop))
        cursor = stop
    return windows or [(start, end)]


class IBKRClient:
    """Historical settles via ib_async. Not verified live this session -- no IBKR Gateway/
    TWS is running on this machine (confirmed via a direct port check, see CLAUDE.md).
    Structurally complete and fixture-tested (a mocked ib_async.IB), matching this
    project's own "build both, verify the live one" precedent (Spec 18's own instruction)."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ) -> None:
        self._host = host if host is not None else settings.ibkr_host
        self._port = port if port is not None else settings.ibkr_port
        self._client_id = client_id if client_id is not None else settings.ibkr_client_id

    def _connect(self) -> object:
        from ib_async import IB

        ib = IB()
        ib.connect(self._host, self._port, clientId=self._client_id, timeout=45)
        return ib

    def list_contracts(self, root: str) -> list[ContractMeta]:
        from ib_async import Future

        specs = load_contract_specs().set_index("root").loc[root].to_dict()
        ib = self._connect()
        try:
            future = Future(symbol=root.upper(), exchange=specs["exchange"])
            details = ib.reqContractDetails(future)  # type: ignore[attr-defined]
        finally:
            ib.disconnect()  # type: ignore[attr-defined]

        contracts = []
        for d in details:
            contract = d.contract.localSymbol.lower()
            expiry_str = d.contract.lastTradeDateOrContractMonth
            contracts.append(
                ContractMeta(
                    root=root,
                    contract=contract,
                    expiry=pd.Timestamp(expiry_str).date(),
                    tick_size=float(specs["tick_size"]),
                    contract_unit=str(specs["contract_unit"]),
                    currency=str(specs["currency"]),
                )
            )
        return contracts

    def get_settles(
        self, root: str, contracts: list[str], start: date, end: date
    ) -> pd.DataFrame:
        from ib_async import Future

        specs = load_contract_specs().set_index("root").loc[root].to_dict()
        ib = self._connect()
        rows = []
        try:
            for contract in contracts:
                # Per-contract failure isolation -- one bad contract must never abort the
                # rest of the root, same pattern pipelines/entsoe's own pull scripts use.
                try:
                    future = Future(
                        symbol=root.upper(),
                        localSymbol=contract.upper(),
                        exchange=specs["exchange"],
                    )
                    # Chunked: a single multi-decade durationStr is rejected by IB.
                    for window_start, window_end in duration_windows(start, end):
                        bars = ib.reqHistoricalData(  # type: ignore[attr-defined]
                            future,
                            endDateTime=window_end,
                            durationStr=f"{(window_end - window_start).days + 1} D",
                            barSizeSetting="1 day",
                            whatToShow="TRADES",
                            useRTH=True,
                            timeout=45,
                        )
                        for bar in bars:
                            rows.append(
                                {
                                    "date": pd.Timestamp(bar.date),
                                    "root": root,
                                    "contract": contract,
                                    "settle": float(bar.close),
                                    "oi": None,
                                    "volume": float(bar.volume),
                                }
                            )
                except Exception as exc:
                    record_failure(f"{root} {contract}", exc)
        finally:
            ib.disconnect()  # type: ignore[attr-defined]

        return pd.DataFrame(rows, columns=["date", "root", "contract", "settle", "oi", "volume"])


class ManualCSVClient:
    """Reads data/manual/futures/settles_YYYYMMDD.csv (git-ignored, hand-dropped) --
    columns date, root, contract, settle, oi, volume, expiry. This is the live,
    verifiable-today client this session (FUTURES_SOURCE=manual) -- but no real
    settlement data has been supplied yet, so real verification is deferred; see
    CLAUDE.md."""

    def __init__(self, data_dir: Path = MANUAL_FUTURES_DIR) -> None:
        self._data_dir = data_dir

    def _read_all_csvs(self) -> pd.DataFrame:
        files = sorted(self._data_dir.glob("settles_*.csv"))
        if not files:
            return pd.DataFrame(columns=_SETTLES_COLUMNS)

        frames = [pd.read_csv(f) for f in files]
        combined = pd.concat(frames, ignore_index=True)
        # Parse date BEFORE validating -- a duplicate-row check on raw date strings
        # would miss two rows for the same real calendar day written differently
        # across separate drops (e.g. a corrected re-drop as "2026-9-1" vs the
        # original "2026-09-01"); normalising first makes the check exact.
        combined["date"] = pd.to_datetime(combined["date"])
        self._validate(combined)
        return combined

    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        missing = set(_SETTLES_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        for col in ("settle", "oi", "volume"):
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise ValueError(f"column {col!r} must be numeric, got dtype {df[col].dtype}")

        # Keyed on (date, root, contract), not just (date, contract) -- contract
        # codes are month+year only (e.g. "z26"), shared across every root trading
        # that expiry cycle, so cl/z26 and ng/z26 on the same real date are both
        # genuinely valid rows, not a duplicate (confirmed by this pipeline's own
        # test_settles_to_ts_long_shape, which constructs exactly that as valid).
        duplicated = df.duplicated(subset=["date", "root", "contract"], keep=False)
        if duplicated.any():
            dupes = df.loc[duplicated, ["date", "root", "contract"]].drop_duplicates()
            raise ValueError(f"duplicate (date, root, contract) rows: {dupes.to_dict('records')}")

        # A contract code shaped like a nearby rank is ambiguous once it becomes a
        # series_id -- see looks_like_rank_code. Reject at ingestion rather than let it
        # silently masquerade as a rank in the lake.
        ambiguous = sorted({c for c in df["contract"].astype(str) if looks_like_rank_code(c)})
        if ambiguous:
            raise ValueError(
                f"contract codes collide with the nearby-rank namespace f01..f36: "
                f"{ambiguous}. Use a four-digit year (e.g. 'f2027', not 'f27')."
            )

    def list_contracts(self, root: str) -> list[ContractMeta]:
        df = self._read_all_csvs()
        root_rows = df[df["root"] == root]
        if root_rows.empty:
            return []

        specs = load_contract_specs().set_index("root").loc[root].to_dict()
        per_contract = root_rows.groupby("contract")["expiry"].first()
        return [
            ContractMeta(
                root=root,
                # Lowercased explicitly -- an operator's hand-typed CSV isn't
                # guaranteed to use lowercase contract codes the way
                # IBKRClient.list_contracts already normalises them, and a
                # mixed-case code here would break the lake's lowercase-dotted
                # series_id convention once it reaches to_ts_long.py.
                contract=str(contract).lower(),
                expiry=pd.Timestamp(expiry).date(),
                tick_size=float(specs["tick_size"]),
                contract_unit=str(specs["contract_unit"]),
                currency=str(specs["currency"]),
            )
            for contract, expiry in per_contract.items()
        ]

    def get_settles(
        self, root: str, contracts: list[str], start: date, end: date
    ) -> pd.DataFrame:
        df = self._read_all_csvs()
        mask = (
            (df["root"] == root)
            & df["contract"].str.lower().isin(contracts)
            & (df["date"] >= pd.Timestamp(start))
            & (df["date"] <= pd.Timestamp(end))
        )
        result = df.loc[mask, ["date", "root", "contract", "settle", "oi", "volume"]].copy()
        result["contract"] = result["contract"].str.lower()
        return result.reset_index(drop=True)


def get_client() -> FuturesClient:
    if settings.futures_source == "ibkr":
        return IBKRClient()
    return ManualCSVClient()
