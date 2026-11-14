"""Looks up a user's email in WorkOS. Access tokens carry no email, so this runs once per user,
on their first authenticated call, to link them to a pre-seeded user."""

from __future__ import annotations

from typing import Protocol

import httpx

WORKOS_API = "https://api.workos.com"
TIMEOUT_SECONDS = 5.0


class Directory(Protocol):
    async def email_for(self, subject: str) -> str | None: ...


class WorkOSDirectory:
    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=WORKOS_API, timeout=TIMEOUT_SECONDS)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def email_for(self, subject: str) -> str | None:
        if not subject.startswith("user_") or "/" in subject:
            return None
        resp = await self._client.get(f"/user_management/users/{subject}", headers=self._headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        email = resp.json().get("email")
        return str(email).lower() if email else None

    async def close(self) -> None:
        await self._client.aclose()
