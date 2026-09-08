"""EIA API v2 client. Route/facet pattern documented in pipelines/eia/CLAUDE.md.

Never let a raw exception from this client escape: EIA authenticates via an `api_key`
*query parameter*, and requests.HTTPError's default string embeds the full request URL,
so printing one leaks the real key into whatever log caught it (golden rule 1). This is
the same leak pipelines/entsoe/client.py documents hitting live on 2026-08-30, via a
different provider's query-parameter auth. Every error path here goes through
core.failures.raise_sanitised."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests
from core.failures import raise_sanitised
from core.settings import settings

BASE_URL = "https://api.eia.gov/v2"
PAGE_SIZE = 5000

# pandas-style frequency codes used to build a deterministic series_id for routes with
# no series facet at all (see get_operational_series). Falls back to the frequency
# string itself for anything not listed here.
_FREQUENCY_CODES: dict[str, str] = {
    "daily": "D",
    "weekly": "W",
    "monthly": "M",
    "quarterly": "Q",
    "annual": "A",
}


def _normalise_geo(area_name: str) -> str:
    if area_name == "U.S.":
        return "US"
    if area_name.startswith("PADD "):
        return "PADD" + area_name.removeprefix("PADD ")
    return area_name


class EIAClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.eia_api_key

    def _fetch_rows(self, route: str, series: list[str], frequency: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            params: dict[str, Any] = {
                "api_key": self._api_key,
                "frequency": frequency,
                "data[0]": "value",
                "facets[series][]": series,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "offset": offset,
                "length": PAGE_SIZE,
            }
            response = requests.get(f"{BASE_URL}/{route}/data/", params=params, timeout=30)
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise_sanitised(exc)
            page = response.json()["response"]["data"]
            rows.extend(page)

            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return rows

    def _fetch_operational_rows(
        self,
        route: str,
        data_key: str,
        fueltypeid: str,
        sectorid: str,
        locations: list[str],
        frequency: str,
    ) -> list[dict[str, Any]]:
        """Sibling to `_fetch_rows` for routes with no `series` facet at all (confirmed
        live on electricity/electric-power-operational-data -- pipelines/eia/CLAUDE.md).
        Rows are selected by {fueltypeid, sectorid, location} instead of a series id, and
        the value lives under the requested `data[0]` key itself (`data_key`), not under
        a fixed "value" field -- so this cannot reuse `_fetch_rows`'s params shape,
        though the paging loop is identical.

        `locations` may hold several codes -- confirmed live, `facets[location][]`
        accepts a repeated value exactly like `facets[series][]` does elsewhere in this
        client, and each returned row carries its own `location`, so every code is
        fetched in one paged request rather than one request per location."""
        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            params: dict[str, Any] = {
                "api_key": self._api_key,
                "frequency": frequency,
                "data[0]": data_key,
                "facets[fueltypeid][]": fueltypeid,
                "facets[sectorid][]": sectorid,
                "facets[location][]": locations,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "offset": offset,
                "length": PAGE_SIZE,
            }
            response = requests.get(f"{BASE_URL}/{route}/data/", params=params, timeout=30)
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise_sanitised(exc)
            page = response.json()["response"]["data"]
            rows.extend(page)

            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return rows

    def get_operational_series(
        self,
        route: str,
        data_keys: list[str],
        fueltypeid: str,
        sectorid: str,
        locations: list[str],
        frequency: str,
    ) -> pd.DataFrame:
        """For routes shaped like electricity/electric-power-operational-data, which
        (confirmed live) have no `series` facet -- `get_series`/`_fetch_rows` cannot
        reach them at all. A row here is selected by combining `fueltypeid`, `sectorid`
        and `location` facets, one `data_key` (e.g. "cost-per-btu") at a time across all
        of `locations` in a single paged request; that key also names both the value
        column and its `<data_key>-units` unit column in the response, rather than the
        fixed "value"/"units" pair every other route in this client uses.

        EIA gives no series id for this shape at all, so this project mints one per row:
        `ELEC.<DATA_KEY>.<fueltypeid>-<location>-<sectorid>.<freq_code>`, e.g.
        `ELEC.COST_PER_BTU.NG-US-98.M` -- deterministic from the row's own facets,
        documented in pipelines/eia/CLAUDE.md, and permanent once written."""
        pulled_at = datetime.now(UTC)
        freq_code = _FREQUENCY_CODES.get(frequency, frequency)
        frames: list[pd.DataFrame] = []
        for key in data_keys:
            rows = self._fetch_operational_rows(
                route, key, fueltypeid, sectorid, locations, frequency
            )
            # Some real states return a literal null for the latest month rather than
            # being absent (confirmed live, pipelines/eia/CLAUDE.md) -- guard here too,
            # matching get_series's own null handling. Never fabricate a value for these.
            raw_rows, rows = rows, [row for row in rows if row.get(key) is not None]
            dropped = len(raw_rows) - len(rows)
            if dropped:
                # Visible, not silent -- matching core.storage._drop_rows_with_no_value's
                # own rule that a dropped row must be named in the run log.
                print(f"{route} ({key}): dropped {dropped} row(s) with no value", flush=True)
            key_id = key.upper().replace("-", "_")
            frames.append(
                pd.DataFrame(
                    {
                        "series_id": [
                            f"ELEC.{key_id}.{fueltypeid}-{row['location']}-{sectorid}"
                            f".{freq_code}"
                            for row in rows
                        ],
                        "source": "eia",
                        "ts": pd.to_datetime([row["period"] for row in rows]),
                        "value": [float(row[key]) for row in rows],
                        "unit": [row[f"{key}-units"] for row in rows],
                        "geo": [row["location"] for row in rows],
                        "freq": frequency,
                        "revision_date": pulled_at,
                    }
                )
            )
        return pd.concat(frames, ignore_index=True)

    def list_series(self, route: str) -> list[dict[str, str]]:
        """List every series id/name available under a route, via its facet endpoint.
        Use this to discover series codes instead of guessing them."""
        params = {"api_key": self._api_key}
        response = requests.get(f"{BASE_URL}/{route}/facet/series", params=params, timeout=30)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise_sanitised(exc)
        result: list[dict[str, str]] = response.json()["response"]["facets"]
        return result

    def get_series(
        self,
        route: str,
        series: list[str],
        frequency: str,
        geo_map: dict[str, str] | None = None,
    ) -> pd.DataFrame:
        """`geo_map`: some routes (e.g. natural-gas/stor/wkly, confirmed live) never
        populate `area-name` at all — it comes back as the literal string "NA" for
        every row, not a genuine missing-value case. Pass an explicit
        {series_id: geo_label} map for those routes instead of relying on
        `_normalise_geo(area-name)`. Default None preserves every existing caller's
        area-name-based behaviour unchanged."""
        rows = self._fetch_rows(route, series, frequency)
        # EIA genuinely returns a literal null `value` for some early-history rows
        # (confirmed live on natural-gas/pri/sum and pri/rescom, pipelines/eia/CLAUDE.md)
        # -- float(None) would crash a full-history pull outright. Skipped here, matching
        # the convention core/storage.py's write_ts_long already applies on the write side.
        raw_rows, rows = rows, [row for row in rows if row.get("value") is not None]
        dropped = len(raw_rows) - len(rows)
        if dropped:
            # Visible, not silent -- matching core.storage._drop_rows_with_no_value's own
            # rule that a dropped row must be named in the run log, not swallowed here.
            print(f"{route}: dropped {dropped} row(s) with no value", flush=True)
        pulled_at = datetime.now(UTC)
        if geo_map is not None:
            geo = [geo_map[row["series"]] for row in rows]
        else:
            geo = [_normalise_geo(row.get("area-name", "")) for row in rows]
        return pd.DataFrame(
            {
                "series_id": [row["series"] for row in rows],
                "source": "eia",
                "ts": pd.to_datetime([row["period"] for row in rows]),
                "value": [float(row["value"]) for row in rows],
                "unit": [row["units"] for row in rows],
                "geo": geo,
                "freq": frequency,
                "revision_date": pulled_at,
            }
        )

    def get_flows(
        self,
        route: str,
        corridors: dict[str, tuple[str, str, str]],
        frequency: str,
    ) -> pd.DataFrame:
        """Like get_series, but returns `flows`-schema rows. `corridors` maps each
        series id to (from_node, to_node, mode)."""
        rows = self._fetch_rows(route, list(corridors), frequency)
        # Same guard as get_series: a null `value` here would otherwise crash this
        # method's unguarded float() outright (pre-existing asymmetry -- get_series
        # was hardened for this, this sibling wasn't; matched here for consistency).
        raw_rows, rows = rows, [row for row in rows if row.get("value") is not None]
        dropped = len(raw_rows) - len(rows)
        if dropped:
            print(f"{route}: dropped {dropped} row(s) with no value", flush=True)
        return pd.DataFrame(
            {
                "source": "eia",
                "from_node": [corridors[row["series"]][0] for row in rows],
                "to_node": [corridors[row["series"]][1] for row in rows],
                "value": [float(row["value"]) for row in rows],
                "unit": [row["units"] for row in rows],
                "ts": pd.to_datetime([row["period"] for row in rows]),
                "mode": [corridors[row["series"]][2] for row in rows],
            }
        )
