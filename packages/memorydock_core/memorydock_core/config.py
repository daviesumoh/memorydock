"""Settings loaded from the environment (and `.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SHARED_DB = "memorydock"
# Developer, integration-test and verification databases. Anything else in dev is a typo
# or the shared database, and a dev run must never write to the shared one.
DEV_DB_PREFIXES = ("memorydock_dev_", "memorydock_test_", "memorydock_verify")


class MissingSetting(RuntimeError):
    def __init__(self, env_var: str) -> None:
        super().__init__(f"{env_var} is not set")
        self.env_var = env_var


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    env: Literal["dev", "prod"] = "dev"
    mongodb_uri: SecretStr | None = None
    mongodb_uri_worker: SecretStr | None = None
    mongodb_uri_admin: SecretStr | None = None
    mongodb_db: str = ""

    @model_validator(mode="after")
    def _database_matches_env(self) -> Settings:
        db = self.mongodb_db
        if not db:
            return self
        if self.env == "prod" and db != SHARED_DB:
            raise ValueError(f"ENV=prod requires MONGODB_DB={SHARED_DB}")
        if self.env == "dev" and not db.startswith(DEV_DB_PREFIXES):
            raise ValueError(
                "ENV=dev requires MONGODB_DB to start with one of: " + ", ".join(DEV_DB_PREFIXES)
            )
        return self

    def require_secret(self, field: str) -> str:
        value = getattr(self, field)
        if value is None or not value.get_secret_value():
            raise MissingSetting(field.upper())
        return str(value.get_secret_value())

    def require_db(self) -> str:
        if not self.mongodb_db:
            raise MissingSetting("MONGODB_DB")
        return self.mongodb_db


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
