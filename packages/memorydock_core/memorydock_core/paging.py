"""Opaque list cursors: base64url JSON {"k": <last key>, "v": 1}.

A malformed or tampered cursor is rejected with invalid_cursor, never served as a wrong page.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

from memorydock_core.errors import InvalidInput

CURSOR_VERSION = 1
MAX_LIMIT = 100
DEFAULT_LIMIT = 50
MAX_CURSOR_LENGTH = 512


def _invalid() -> InvalidInput:
    return InvalidInput("cursor is not valid for this list", field="cursor", code="invalid_cursor")


def encode_cursor(key: str | int) -> str:
    raw = json.dumps({"k": key, "v": CURSOR_VERSION}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, *, pattern: str | None = None, integer: bool = False) -> str | int:
    """Return the key, checked against the id `pattern` or as a non-negative integer."""
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise _invalid()
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        doc: Any = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise _invalid() from None
    if not isinstance(doc, dict) or set(doc) != {"k", "v"} or doc["v"] != CURSOR_VERSION:
        raise _invalid()
    key = doc["k"]
    if integer:
        # bool is an int subclass; a cursor of true must not read as 1.
        if type(key) is not int or key < 0:
            raise _invalid()
        return key
    if not isinstance(key, str) or pattern is None or re.fullmatch(pattern, key) is None:
        raise _invalid()
    return key
