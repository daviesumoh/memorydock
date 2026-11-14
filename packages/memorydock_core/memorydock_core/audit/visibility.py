"""Which audit entries a viewer sees. The list route, the live stream and explain_decision all
use this one function."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any, Literal

Visibility = Literal["full", "placeholder", "hidden"]


def visibility(
    entry: Mapping[str, Any],
    *,
    viewer_user_id: str,
    readable_scopes: Collection[str],
    is_org_admin: bool,
) -> Visibility:
    actor = entry.get("actor") or {}
    if actor.get("user_id") == viewer_user_id:
        return "full"
    keys = list((entry.get("resource") or {}).get("scope_keys") or [])
    if keys and all(k in readable_scopes for k in keys):
        return "full"
    if not is_org_admin:
        return "hidden"
    if keys and any(k.startswith("user:") and k not in readable_scopes for k in keys):
        # Another user's personal activity: admins see that it happened, not what it touched.
        return "placeholder"
    return "full"
