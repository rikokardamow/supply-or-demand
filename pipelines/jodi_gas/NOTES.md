# pipelines/jodi_gas — notes

JODI-Gas World Database through the JODI REST API v1.2. **Needs a free jodidata.org account**:
`JODI_USERNAME` (the sign-up email) and `JODI_PASSWORD` in `.env`, read via `core.settings`.
`core.failures` redacts `*_password` fields. `python -m pipelines.jodi_gas.pull` writes
`source="jodi_gas"`, `jodi_gas.<flow>.<country>`, mcm, monthly from 2010.
Consumer: `pipelines/derived/lng.py`.

## Confirmed live 2026-10-26

- `POST https://www.jodidata.org/api/token` with a **form-encoded** body. A JSON body returns
  400. The response is `{token, username, expires}`, and the token lasts one hour.
- `GET /api/gasdata` with `Authorization: Bearer <token>`, filtered by `countries`,
  `products`, `flows`, `units`, `dateFrom`, `dateTo` (yyyy-MM), and paged by `pageSize`
  (≤ 100,000) and `pageNumber`. The response is `{data: [...], meta: {hasNext, totalPages, ...}}`.
  The rate limit is 100 requests a minute (`X-Rate-Limit-*` headers).
- **LNG is product `NATGAS` with flows `IMPLNG` / `EXPLNG`.** Product `LNG` returns nothing.
  Unit `M3` is million m3. The full pull (6 flows, 2010→) is one page, 74,796 rows from 94 countries.
- The bulk `jodi_gas_csv_beta.zip` on the downloads page stops in 2018-08. Never use it.

## Data traps

- Reporting lags differ by country (India to 2026-03, China 2026-07, Japan 2026-08 in the
  2026-10-26 run). World totals need the coverage rule in `core.lng_balance.coverage`.
- Taiwan files 0 for LNG imports in every month (58 of 58). It is treated as unreported
  (`ZERO_IS_UNREPORTED`).
- Greece is `GR` here and `EL` at Eurostat.
- Russia does not report LNG exports.

## No cassette, on purpose

The token request carries the username and password in its form body, and a recording would
put them in a public file. `tests/test_jodi_gas_client.py` replaces HTTP instead.
