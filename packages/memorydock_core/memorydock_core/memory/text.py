"""Normalising memory text so that the same idea hashes the same way everywhere: exact-duplicate
detection, the forget blocklist and the audit log all use content_hash."""

from __future__ import annotations

import hashlib
import re
import unicodedata

EMBED_TEXT_MAX = 2000
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip().casefold()


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def embed_text(content: str) -> str:
    """What the vector index embeds. The model's input limit is far above this, but the
    validator caps the field so a single memory can't dominate embedding cost."""
    return content.strip()[:EMBED_TEXT_MAX]
