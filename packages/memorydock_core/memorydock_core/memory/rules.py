"""The numbers that shape trust, lifetime and ranking. Recall builds its aggregation stages from
these tables, so this module is the only place they are tuned."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from memorydock_core.models.common import MemoryStatus, MemoryType, ScopeLevel, TrustRank

TRUST_WEIGHT: Final[dict[TrustRank, float]] = {
    "user_stated": 1.00,
    "user_confirmed": 0.95,
    "extracted_user": 0.85,
    "agent_inferred": 0.70,
}
TRUST_ORDER: Final[tuple[TrustRank, ...]] = tuple(TRUST_WEIGHT)

# A new memory starts at its trust weight; flags and duplicates move it from there.
INITIAL_CONFIDENCE: Final[dict[TrustRank, float]] = dict(TRUST_WEIGHT)

DEFAULT_EXPIRY: Final[dict[MemoryType, timedelta]] = {
    "open_question": timedelta(days=14),
    "episode": timedelta(days=30),
}

# None means the type does not decay.
HALF_LIFE_DAYS: Final[dict[MemoryType, float | None]] = {
    "fact": 180,
    "decision": None,
    "preference": None,
    "procedure": None,
    "finding": 90,
    "open_question": 30,
    "episode": 14,
}

RECALLABLE: Final[tuple[MemoryStatus, ...]] = ("active", "conflict", "disputed")

# Weight of each scope level in recall. "project" means the project the caller is focused on;
# other projects get OTHER_PROJECT_WEIGHT.
SCOPE_WEIGHT: Final[dict[ScopeLevel, float]] = {
    "user": 1.0,
    "project": 1.0,
    "team": 0.8,
    "org": 0.7,
}
OTHER_PROJECT_WEIGHT: Final = 0.6

INSTRUCTION_LIKE_FACTOR: Final = 0.5
STATUS_FACTOR: Final[dict[MemoryStatus, float]] = {"disputed": 0.4, "conflict": 0.8}

# Candidates scoring under this share of the best one are dropped.
RELATIVE_CUTOFF: Final = 0.2

# Each search branch's candidate pool before fusion.
BRANCH_LIMIT: Final = 60
VECTOR_CANDIDATES: Final = 200
FUSION_WEIGHTS: Final = {"vec": 1.0, "text": 0.6}

# Clients that run inside work sessions; they skip memories whose category is not for work.
WORK_CLIENTS: Final = frozenset({"claude-code", "codex"})
