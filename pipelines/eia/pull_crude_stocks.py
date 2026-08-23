"""Pull weekly US crude stocks (ex-SPR) and Cushing stocks, full history, into the lake."""

from __future__ import annotations

from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

ROUTE = "petroleum/stoc/wstk"
SERIES = ["WCESTUS1", "W_EPC0_SAX_YCUOK_MBBL"]


def main() -> None:
    client = EIAClient()
    df = client.get_series(route=ROUTE, series=SERIES, frequency="weekly")
    write_ts_long(df, source="eia")
    print(f"wrote {len(df)} rows for series {SERIES}")


if __name__ == "__main__":
    main()
