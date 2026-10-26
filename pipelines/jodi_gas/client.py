"""JODI-Gas World Database via the JODI REST API (v1.2). Needs a free jodidata.org account.

Confirmed live 2026-10-26 (see this package's NOTES.md):

- ``POST /api/token`` with **form-encoded** ``username`` and ``password`` (a JSON body gets
  400) returns ``{"token", "username", "expires"}``. The token is good for one hour.
- ``GET /api/gasdata`` with a Bearer token and ``countries``, ``products``, ``flows``,
  ``units``, ``dateFrom``/``dateTo`` (yyyy-MM) and ``pageSize`` (100 to 100,000) /
  ``pageNumber`` returns ``{"data": [...], "meta": {"totalPages", "hasNext", ...}}``. Rows
  carry ``country``, ``product``, ``flow``, ``unit``, ``date``, ``quantity`` and ``quality``.
- LNG is product ``NATGAS`` with flows ``IMPLNG`` / ``EXPLNG``. Product ``LNG`` returns
  nothing. Unit ``M3`` is million m3, ``TJ`` is terajoules.
- The rate limit is 100 requests a minute.

The bulk ``jodi_gas_csv_beta.zip`` on the downloads page stops in 2018-08: do not use it.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import requests
from core.failures import raise_sanitised
from core.settings import settings

BASE_URL = "https://www.jodidata.org/api"
REQUEST_TIMEOUT_SECONDS = 120
PAGE_SIZE = 100_000


class JodiGasClient:
    def __init__(self, username: str | None = None, password: str | None = None) -> None:
        self._username = username or settings.jodi_username
        self._password = password or settings.jodi_password
        if not self._username or not self._password:
            raise ValueError("JODI_USERNAME and JODI_PASSWORD must be set in .env")
        self._token: str | None = None

    def _auth(self) -> dict[str, str]:
        if self._token is None:
            response = requests.post(
                f"{BASE_URL}/token",
                data={"username": self._username, "password": self._password},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise_sanitised(exc)
            self._token = str(response.json()["token"])
        return {"Authorization": f"Bearer {self._token}"}

    def gas_data(self, **filters: str) -> pd.DataFrame:
        """Every row matching ``filters`` (API parameter names), across all pages."""
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            response = requests.get(
                f"{BASE_URL}/gasdata",
                headers=self._auth(),
                params={**filters, "pageSize": str(PAGE_SIZE), "pageNumber": str(page)},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise_sanitised(exc)
            body = response.json()
            rows.extend(body["data"])
            if not body["meta"].get("hasNext"):
                break
            page += 1
        return pd.DataFrame(
            rows, columns=["country", "product", "flow", "unit", "date", "quantity", "quality"]
        )
