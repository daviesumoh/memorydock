import secrets
from collections.abc import Iterator
from typing import Any

import pytest
from memorydock_core.config import MissingSetting, Settings
from memorydock_core.db import sync_client
from pymongo import MongoClient


@pytest.fixture(scope="session")
def admin_client() -> Iterator[MongoClient[dict[str, Any]]]:
    try:
        uri = Settings().require_secret("mongodb_uri_admin")
    except MissingSetting:
        pytest.skip("MONGODB_URI_ADMIN is not set")
    client = sync_client(uri, app_name="memorydock-tests")
    yield client
    client.close()


@pytest.fixture
def test_db_name(admin_client: MongoClient[dict[str, Any]]) -> Iterator[str]:
    # Each run gets its own database and drops only that one.
    name = f"memorydock_test_{secrets.token_hex(4)}"
    yield name
    admin_client.drop_database(name)
