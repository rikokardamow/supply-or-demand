---
description: Scaffold a new data pipeline (client + CLAUDE.md + cassette test) under pipelines/<source>/
---

Scaffold a new pipeline for source: $ARGUMENTS

Read `CLAUDE.md` and the relevant spec under `specs/` for this source before writing
anything. Follow the pattern already established in `pipelines/eia/`.

Create:
1. `pipelines/<source>/__init__.py` (empty).
2. `pipelines/<source>/client.py` — a `<Source>Client` class, matching the shape of
   `pipelines/eia/client.py`: constructor takes an optional credentials param falling back
   to `core.settings.settings`; a method that fetches data and returns a
   `core.schemas`-conformant DataFrame (`ts_long` or `flows` — check the spec for which).
   Never log or print a full request URL, params dict, or raw response that could contain a
   credential. **Check live whether this API echoes the credential back in the response
   body** (EIA does, under `response.request.params.api_key` — see
   `pipelines/eia/CLAUDE.md`) before assuming it's safe to print/record unfiltered.
3. `pipelines/<source>/CLAUDE.md` — document the endpoint/route pattern, pagination or
   rate-limit behaviour, auth quirks, and which series/fields are used so far, following the
   structure of `pipelines/eia/CLAUDE.md`.
4. `tests/test_<source>_client.py` — a `@pytest.mark.vcr` test recording a cassette into
   `tests/cassettes/`. Reuse `tests/conftest.py`'s `vcr_config` fixture (filters `api_key`
   from the request) and add a `before_record_response` scrub for this API if it echoes any
   credential back in the response body.
5. If this pipeline writes to the lake, add a `pull_<something>.py` entrypoint mirroring
   `pipelines/eia/pull_crude_stocks.py`.

Before considering the cassette safe to commit, confirm:
`git grep -iE "api_key.*=.*[A-Za-z0-9]{20}" -- ':!*.example'` returns nothing (run with
`--untracked` too, since a new cassette isn't staged yet).

Plan first, then implement. Run `pytest`, `ruff check .`, and `mypy core pipelines` before
considering this done.
