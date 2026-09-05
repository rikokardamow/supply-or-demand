# Spec 28 (GRP) — Adaptation Contract

Spec 28 was written against a Postgres 16 + pgvector / FastAPI / Grafana / docker-compose platform that does not exist in this repo. The decision made on 5 September 2026 is to adapt Spec 28 onto the repo's real DuckDB + Parquet + Streamlit + `infra/run_scheduled.py` stack. This follows the precedent already established for `weather-module-spec.md`, which was also written against Railway/Postgres/Grafana and adapted the same way (see `README.md:766`, `CHANGELOG.md:247`, `pipelines/weather/NOTES.md:221`). Every Spec 28 session must read this file before starting and must not re-litigate the decision.

## Adaptation table

| Spec 28 construct | Adapted target in this repo |
|---|---|
| Postgres schema `grp`, DDL in `grp/store/migrations/0001_grp_schema.sql` (28.02) | Parquet state tables under `data/lake/grp/`, schemas in `core/schemas.py` following the `SANCTIONS_SCHEMA` precedent (a state table, **not** `_write_partitioned`) |
| `grp.scores` rows | `ts_long` series `grp.gulf.score`, `.escalation`, `.taco`, `.airspace`, `.physical`, `.crowded` written by `write_ts_long(df, source="grp")` |
| pgvector `vector(384)` + `<=>` cosine | The spec's **own documented fallback** (28.02 §1, 28.03 §6): store embeddings as a float32 list column, compute cosine in Python over the dedup window only |
| PostGIS `geometry(Polygon,4326)` | The spec's own fallback: `bbox` as JSON + shapely. PostGIS is optional in the spec's own v1 anyway |
| `api/routers/grp.py`, `api/models/grp.py`, `X-GRP-TOKEN` write endpoints (28.09) | **Dropped.** Page `28_grp.py` reads the lake directly (rule 2). The two write endpoints become Streamlit forms on the review table — no network surface, so no write token exists to leak |
| Grafana dashboard `grp.json`, 10 panels, alerts (28.10) | `apps/dashboard/pages/28_grp.py`: one `card()` per panel using `core/theme.py` primitives; panel 8 geomap → `go.Scattermapbox` open-street-map reusing `components/news_map.py`; the alert engine → `pipelines/grp/alerts.py` writing `events` rows surfaced by the existing `components/event_overlay.py` |
| `docker-compose.yml`, `grp/jobs/scheduler.py` APScheduler, `make` targets (28.11) | A new `grp_fast` cadence in `infra/run_scheduled.py`'s `CADENCE_GROUPS`, registered by `infra/register_tasks.ps1`. The `Makefile` gains no Docker targets |
| Alembic / `make migrate` | None. Parquet schema evolution as the repo already does it |
| Railway mapping (28.11 §6, Phase 4) | Deferred to Phase 7. Note `railway.toml` is **stale** — it starts `src/kardamow/app/main.py` and `scripts.run_ingestors`, neither of which exists |
| "Reads the repo's `eia` schema" (28.06) | `core.storage.read_ts_long([...])` against real `eia.*` series IDs — verify each against the live lake first, per `00_TRADING_CONVENTIONS.md`'s own "checked live, not assumed" rule |
| "Brent curve from `markets`" (28.07) | `core/curve.py` plus the `fut.*` / `derived.curve.*` series Spec 18 already writes |
| CFTC COT (28.07) | `pipelines/cftc/` already exists — reuse, do not duplicate |
| NewsAPI / WorldNews / GDELT ingestion, dedup, classify (28.03) | **Extend `pipelines/news/`**, which already has `client.py`, `newsapi_client.py`, `guardian_client.py`, `dedup.py`, `tagging.py`, `translate.py` and their tests. Spec 28.06 states the rule itself: "Do not duplicate ingestion" |
| `sentence-transformers` MiniLM embeddings, pre-baked into a Docker layer | **New dependency — needs approval (rule 7).** First try `pipelines/news/dedup.py`, which already passes `tests/test_news_dedup.py`. Only add the model if that measurably fails GRP's dedup acceptance criteria |
| Anthropic LLM classifier (28.03) | Keep as specced — `anthropic>=0.40` is already a dependency |
| AISStream websocket service (28.05) | Requires Spec 11, which is unbuilt → Phase 5 |
| FAA NOTAM + OpenSky (28.04) | Requires Spec 12, which is unbuilt → Phase 5 |

## Open items

- `sentence-transformers` is a new dependency and needs the repo owner's approval per root NOTES.md rule 7; try `pipelines/news/dedup.py` first.
- Specs 11 (AIS) and 12 (flights) are unbuilt and are hard prerequisites for GRP components 28.04 (airspace) and 28.05 (maritime).
- `railway.toml` is stale — it starts `src/kardamow/app/main.py` and `scripts.run_ingestors`, neither of which exists.
