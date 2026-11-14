"""Prefixed ULID ids, e.g. mem_01JD3X...; sortable by creation time."""

from __future__ import annotations

import re

from ulid import ULID

PREFIXES = frozenset({
    "mem", "memv", "turn", "ses", "lease", "task", "step", "eff", "apr", "aud", "msg", "exp",
    "drf", "ctr", "usr", "prj", "team", "map", "pol", "ent", "rec", "fbl", "rev", "cat", "seg",
    "req",
})  # fmt: skip


def new_id(prefix: str) -> str:
    if prefix not in PREFIXES:
        raise ValueError(f"unknown id prefix {prefix!r}")
    return f"{prefix}_{ULID()}"


def id_pattern(prefix: str) -> str:
    return rf"^{prefix}_[0-9A-HJKMNP-TV-Z]{{26}}$"


def is_id(value: str, prefix: str) -> bool:
    return re.fullmatch(id_pattern(prefix), value) is not None
