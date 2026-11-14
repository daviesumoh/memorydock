"""Check each configured database user can connect. Prints user, roles and PASS/FAIL only."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from memorydock_core.config import MissingSetting, Settings
from memorydock_core.db import redact_uris, sync_client
from pydantic import ValidationError

URIS = [
    ("admin", "mongodb_uri_admin"),
    ("gateway", "mongodb_uri"),
    ("worker", "mongodb_uri_worker"),
]


@dataclass(frozen=True)
class Result:
    label: str
    ok: bool
    detail: str

    def __str__(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'} {self.label}: {self.detail}"


def describe_auth(status: dict[str, Any]) -> str:
    info = status.get("authInfo", {})
    users = [u.get("user", "?") for u in info.get("authenticatedUsers", [])]
    roles = sorted(f"{r.get('role')}@{r.get('db')}" for r in info.get("authenticatedUserRoles", []))
    return f"user {', '.join(users) or 'none'}; roles {', '.join(roles) or 'none'}"


def check_one(label: str, uri: str, connect: Callable[[str], Any]) -> Result:
    try:
        client = connect(uri)
        try:
            client.admin.command("ping")
            status = client.admin.command({"connectionStatus": 1})
        finally:
            client.close()
    except Exception as exc:  # every failure becomes a FAIL line
        return Result(label, False, f"{type(exc).__name__}: {redact_uris(str(exc))[:200]}")
    return Result(label, True, describe_auth(status))


def run(settings: Settings, connect: Callable[[str], Any]) -> list[Result]:
    results = []
    for label, field in URIS:
        try:
            uri = settings.require_secret(field)
        except MissingSetting as exc:
            results.append(Result(label, False, str(exc)))
            continue
        results.append(check_one(label, uri, connect))
    try:
        results.append(Result("database", True, settings.require_db()))
    except MissingSetting as exc:
        results.append(Result("database", False, str(exc)))
    return results


def main() -> int:
    try:
        settings = Settings()
    except ValidationError as exc:
        for err in exc.errors():
            print(f"FAIL settings: {err['msg']}")
        return 1
    results = run(settings, lambda uri: sync_client(uri, app_name="memorydock-check-env"))
    for result in results:
        print(result)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
