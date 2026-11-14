"""Settings loaded from the environment (and `.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SHARED_DB = "memorydock"
# Developer, integration-test and verification databases. Anything else in dev is a typo
# or the shared database, and a dev run must never write to the shared one.
DEV_DB_PREFIXES = ("memorydock_dev_", "memorydock_test_", "memorydock_verify")


def check_database_for_env(env: str, database: str) -> None:
    if env == "prod" and database != SHARED_DB:
        raise ValueError(f"ENV=prod requires the {SHARED_DB} database")
    if env == "dev" and not database.startswith(DEV_DB_PREFIXES):
        raise ValueError("ENV=dev requires a database starting with " + ", ".join(DEV_DB_PREFIXES))


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

    autoembed_model: str = "voyage-4"
    gateway_base_url: str = "http://127.0.0.1:8000"
    console_origin: str = "http://localhost:3000"
    extension_origin: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    git_sha: str = ""
    authkit_domain: str = ""
    workos_client_id: str = ""
    workos_api_key: SecretStr | None = None
    identity_cache_seconds: int = 15
    recall_token_budget: int = Field(default=1500, ge=100, le=20000)

    @model_validator(mode="after")
    def _database_matches_env(self) -> Settings:
        if self.mongodb_db:
            check_database_for_env(self.env, self.mongodb_db)
        return self

    def require_secret(self, field: str) -> str:
        value = getattr(self, field)
        if value is None or not value.get_secret_value():
            raise MissingSetting(field.upper())
        return str(value.get_secret_value())

    def require_authkit_domain(self) -> str:
        if not self.authkit_domain:
            raise MissingSetting("AUTHKIT_DOMAIN")
        return self.authkit_domain.rstrip("/")

    def require_db(self) -> str:
        if not self.mongodb_db:
            raise MissingSetting("MONGODB_DB")
        return self.mongodb_db


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
