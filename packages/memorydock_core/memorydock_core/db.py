"""MongoDB client construction. Only this module and the repository layer open connections."""

from __future__ import annotations

import re
from typing import Any

from pymongo import AsyncMongoClient, MongoClient
from pymongo.asynchronous.database import AsyncDatabase

SERVER_SELECTION_TIMEOUT_MS = 5_000
CONNECT_TIMEOUT_MS = 5_000

_URI = re.compile(r"mongodb(?:\+srv)?://\S+")


def redact_uris(text: str) -> str:
    """Driver errors can echo the connection string; strip it before anything is printed."""
    return _URI.sub("<uri>", text)


def sync_client(uri: str, *, app_name: str) -> MongoClient[dict[str, Any]]:
    return MongoClient(
        uri,
        appname=app_name,
        serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=CONNECT_TIMEOUT_MS,
        tz_aware=True,
    )


def async_client(uri: str, *, app_name: str) -> AsyncMongoClient[dict[str, Any]]:
    return AsyncMongoClient(
        uri,
        appname=app_name,
        serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=CONNECT_TIMEOUT_MS,
        tz_aware=True,
    )


async def ping(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db.command("ping")
