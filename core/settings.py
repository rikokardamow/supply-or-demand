"""Application settings loaded from .env. Never print or log these values."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    eia_api_key: str
    ember_api_key: str
    gie_api_key: str
    entsoe_api_key: str
    fred_api_key: str

    newsapi_key: str | None = None
    worldnews_key: str | None = None
    aisstream_key: str | None = None
    opensky_client_id: str | None = None
    opensky_client_secret: str | None = None
    mapbox_token: str | None = None
    tomorrow_io_key: str | None = None
    guardian_key: str | None = None
    adanos_api_key: str | None = None
    anthropic_api_key: str | None = None

    # pipelines/futures -- IBKR Gateway/TWS connection params, not a secret (auth is
    # handled by the locally-running Gateway app itself, no API key involved). Plain
    # defaults are safe since a wrong value just fails to connect, matching every
    # other optional-dependency client in this project.
    futures_source: Literal["ibkr", "manual"] = "manual"
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1

    # Spec 32 -- Supabase serving-layer publish. Pooler connection string (transaction
    # mode, port 6543), database-owner credential -- never the anon/authenticated roles.
    # Optional: only pipelines calling core.publish.publish() need it; every other
    # pipeline and the Streamlit app run unaffected without it set.
    supabase_db_url: str | None = None
    # Spec 32/33 -- set once web/ exists and pipelines start calling the revalidate hook.
    revalidate_secret: str | None = None
    vercel_url: str | None = None


settings = Settings()
