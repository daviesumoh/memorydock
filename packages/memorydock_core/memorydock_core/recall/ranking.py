"""The recall aggregation's stages, generated from the tables in memory.rules.

Search finds candidates with every eligibility rule applied as a pre-filter in both branches,
then the live documents are re-checked (search indexes lag writes), re-scored and cut.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from memorydock_core.memory import rules

WINDOW_ALL = {"documents": ["unbounded", "unbounded"]}
SECONDS_PER_DAY = 86_400

# What recall hands back; content-free fields plus the text to inject.
RESULT_FIELDS = (
    "scope_key", "scope_level", "type", "status", "content", "trust", "provenance.actor_user",
    "provenance.source_client", "category_rules", "instruction_like", "validity", "created_at",
)  # fmt: skip


def search(query: str, *, tenant: str, keys: Sequence[str], work_session: bool) -> dict[str, Any]:
    statuses = list(rules.RECALLABLE)
    vec_filter: dict[str, Any] = {
        "tenant_id": tenant,
        "scope_key": {"$in": list(keys)},
        "status": {"$in": statuses},
    }
    text_filter: list[dict[str, Any]] = [
        {"equals": {"path": "tenant_id", "value": tenant}},
        {"in": {"path": "scope_key", "value": list(keys)}},
        {"in": {"path": "status", "value": statuses}},
    ]
    if work_session:
        vec_filter["inject_in_work"] = True
        text_filter.append({"equals": {"path": "inject_in_work", "value": True}})
    vec = {
        "$vectorSearch": {
            "index": "memory_semantic",
            "path": "embed_text",
            "query": query,
            "filter": vec_filter,
            "numCandidates": rules.VECTOR_CANDIDATES,
            "limit": rules.BRANCH_LIMIT,
        }
    }
    text = {
        "$search": {
            "index": "memory_lexical",
            "compound": {
                "must": [{"text": {"query": query, "path": ["content", "entities.name"]}}],
                "filter": text_filter,
            },
        }
    }
    # Sub-pipelines can't contain $project, so shaping happens after fusion.
    return {
        "$rankFusion": {
            "input": {"pipelines": {"vec": [vec], "text": [text, {"$limit": rules.BRANCH_LIMIT}]}},
            "combination": {"weights": dict(rules.FUSION_WEIGHTS)},
        }
    }


def live_recheck(tenant: str, keys: Sequence[str], now: datetime) -> dict[str, Any]:
    return {
        "$match": {
            "tenant_id": tenant,
            "scope_key": {"$in": list(keys)},
            "status": {"$in": list(rules.RECALLABLE)},
            "$or": [{"validity.expires_at": None}, {"validity.expires_at": {"$gt": now}}],
        }
    }


def _switch(field: str, table: Mapping[Any, Any], default: Any) -> dict[str, Any]:
    return {
        "$switch": {
            "branches": [{"case": {"$eq": [field, k]}, "then": v} for k, v in table.items()],
            "default": default,
        }
    }


def _recency(now: datetime) -> dict[str, Any]:
    age_days = {
        "$divide": [
            {"$dateDiff": {"startDate": "$validity.valid_from", "endDate": now, "unit": "second"}},
            SECONDS_PER_DAY,
        ]
    }
    decaying = {t: hl for t, hl in rules.HALF_LIFE_DAYS.items() if hl}
    return {
        "$switch": {
            "branches": [
                {
                    "case": {"$eq": ["$type", t]},
                    "then": {"$pow": [0.5, {"$divide": [{"$max": [age_days, 0]}, hl]}]},
                }
                for t, hl in decaying.items()
            ],
            "default": 1.0,
        }
    }


def _scope_weight(focus_key: str | None) -> dict[str, Any]:
    weights: dict[str, Any] = {str(k): v for k, v in rules.SCOPE_WEIGHT.items()}
    if focus_key is not None:
        weights["project"] = {
            "$cond": [{"$eq": ["$scope_key", focus_key]}, 1.0, rules.OTHER_PROJECT_WEIGHT]
        }
    return _switch("$scope_level", weights, 0.0)


def rescore(now: datetime, *, focus_key: str | None, limit: int) -> list[dict[str, Any]]:
    """score = rrf_norm x trust x recency x scope x confidence x penalties, cut below a share of
    the best score, best first."""
    return [
        {"$addFields": {"_rrf": {"$meta": "score"}}},
        {
            "$setWindowFields": {
                "sortBy": {"_rrf": -1},
                "output": {"_rrf_max": {"$max": "$_rrf", "window": WINDOW_ALL}},
            }
        },
        {
            "$addFields": {
                "_score": {
                    "$multiply": [
                        {
                            "$cond": [
                                {"$gt": ["$_rrf_max", 0]},
                                {"$divide": ["$_rrf", "$_rrf_max"]},
                                0,
                            ]
                        },
                        _switch("$trust.asserted_by", rules.TRUST_WEIGHT, 0.0),
                        _recency(now),
                        _scope_weight(focus_key),
                        "$trust.confidence",
                        _switch("$status", rules.STATUS_FACTOR, 1.0),
                        {"$cond": ["$instruction_like", rules.INSTRUCTION_LIKE_FACTOR, 1.0]},
                    ]
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"_score": -1},
                "output": {"_score_max": {"$max": "$_score", "window": WINDOW_ALL}},
            }
        },
        {
            "$match": {
                "$expr": {
                    "$gte": ["$_score", {"$multiply": [rules.RELATIVE_CUTOFF, "$_score_max"]}]
                }
            }
        },
        {"$sort": {"_score": -1, "_id": 1}},
        {"$limit": limit},
        {"$project": {**{f: 1 for f in RESULT_FIELDS}, "score": "$_score"}},
    ]


def pipeline(
    query: str,
    *,
    tenant: str,
    keys: Sequence[str],
    work_session: bool,
    focus_key: str | None,
    now: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    return [
        search(query, tenant=tenant, keys=keys, work_session=work_session),
        live_recheck(tenant, keys, now),
        *rescore(now, focus_key=focus_key, limit=limit),
    ]
