"""Application settings loaded from .env. Never print or log these values."""

from __future__ import annotations

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


settings = Settings()
