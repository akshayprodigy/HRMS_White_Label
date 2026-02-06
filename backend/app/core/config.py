from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    # Comma-separated string in env, e.g. "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"

    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "unitederp"
    db_user: str = "unitederp"
    db_password: str = ""

    # Optional override (recommended in Docker/CI):
    database_url: str | None = None

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_path: str = "/"

    @property
    def cors_origins_list(self) -> list[str]:
        return [v.strip() for v in self.cors_origins.split(",") if v.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url

        user = self.db_user
        password = self.db_password
        host = self.db_host
        port = self.db_port
        name = self.db_name
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_nested_delimiter="__",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
