import json

import pytest
from atlas_layout import ATLAS_DIR, UNTENANTED, IndexSpec, load_layout
from atlas_setup import is_subset, key_pairs, plan_indexes

LAYOUT = load_layout({"AUTOEMBED_MODEL": "voyage-4"})

PHASE_1 = {
    "orgs",
    "teams",
    "projects",
    "users",
    "agent_sessions",
    "policies",
    "policy_heads",
    "audit_log",
    "audit_heads",
    "memories",
    "memory_versions",
    "forget_blocklist",
}
COLLECTIONS = PHASE_1 | {"leases"}


def test_every_expected_collection_has_a_validator():
    assert set(LAYOUT.collections) == COLLECTIONS


def test_every_indexed_collection_has_a_validator():
    assert set(LAYOUT.indexes) <= set(LAYOUT.validators)
    assert {s.collection for s in LAYOUT.search_indexes} <= set(LAYOUT.validators)


def _json_schema(validator):
    if "$jsonSchema" in validator:
        return validator["$jsonSchema"]
    return next(part["$jsonSchema"] for part in validator["$and"] if "$jsonSchema" in part)


@pytest.mark.parametrize("name", sorted(COLLECTIONS))
def test_validator_requires_id_and_lists_every_required_property(name):
    schema = _json_schema(LAYOUT.validators[name])
    assert "_id" in schema["required"]
    assert set(schema["required"]) <= set(schema["properties"])


@pytest.mark.parametrize("name", sorted(COLLECTIONS - UNTENANTED))
def test_tenant_collections_require_tenant_id_and_timestamps(name):
    required = set(_json_schema(LAYOUT.validators[name])["required"])
    assert "tenant_id" in required
    if name != "audit_log":  # audit entries carry ts instead
        assert {"created_at", "updated_at"} <= required


def test_tenant_indexes_lead_with_tenant_id():
    # A tenant collection index that does not start with tenant_id can't serve a tenant query.
    allowed = {
        ("memories", "provenance_session"),
        ("memory_versions", "memory_version"),
        ("projects", "repo_remotes"),
        ("users", "idp_sub"),
    }
    for coll, specs in LAYOUT.indexes.items():
        for spec in specs:
            if coll in UNTENANTED or (coll, spec.name) in allowed:
                continue
            assert spec.keys[0][0] == "tenant_id", f"{coll}.{spec.name}"


def test_no_ttl_on_memories():
    assert all(s.ttl_seconds is None for s in LAYOUT.indexes["memories"])


def test_index_names_unique_per_collection():
    for specs in LAYOUT.indexes.values():
        names = [s.name for s in specs]
        assert len(names) == len(set(names))


def test_autoembed_model_is_substituted():
    semantic = next(s for s in LAYOUT.search_indexes if s.name == "memory_semantic")
    assert semantic.type == "vectorSearch"
    embed = semantic.definition["fields"][0]
    assert embed == {
        "type": "autoEmbed",
        "modality": "text",
        "path": "embed_text",
        "model": "voyage-4",
    }
    assert "${" not in json.dumps(semantic.definition)


def test_index_file_keeps_one_spec_per_line():
    lines = (ATLAS_DIR / "indexes.json").read_text().splitlines()
    assert all(line.count('"name"') <= 1 for line in lines)


SPEC = IndexSpec("tenant_slug", (("tenant_id", 1), ("slug", 1)), unique=True)


def info(name, keys, **extra):
    return {"name": name, "key": dict(keys), **extra}


def test_key_pairs_keep_direction_and_order():
    assert key_pairs({"a": 1, "b": -1}) != key_pairs({"a": 1, "b": 1})
    assert key_pairs({"a": 1, "b": 1}) != key_pairs({"b": 1, "a": 1})
    assert key_pairs({"a": 1.0}) == (("a", 1),)


def test_missing_index_is_created():
    assert [a.kind for a in plan_indexes([info("_id_", [("_id", 1)])], [SPEC])] == ["create"]


def test_matching_index_is_ok_even_under_another_name():
    existing = [info("old_name", SPEC.keys, unique=True)]
    assert [a.kind for a in plan_indexes(existing, [SPEC])] == ["ok"]


def test_same_fields_other_direction_is_not_a_match():
    existing = [info("x", [("tenant_id", 1), ("slug", -1)], unique=True)]
    assert [a.kind for a in plan_indexes(existing, [SPEC])] == ["create"]


def test_uniqueness_change_is_a_conflict_not_a_drop():
    existing = [info("tenant_slug", SPEC.keys)]
    actions = plan_indexes(existing, [SPEC])
    assert actions[0].kind == "conflict" and "unique" in actions[0].detail


def test_partial_filter_change_is_a_conflict():
    spec = IndexSpec("p", (("a", 1),), unique=True, partial={"s": {"$in": ["x"]}})
    existing = [info("p", [("a", 1)], unique=True, partialFilterExpression={"s": "x"})]
    assert plan_indexes(existing, [spec])[0].kind == "conflict"


def test_name_taken_by_other_keys_is_a_conflict():
    existing = [info("tenant_slug", [("tenant_id", 1)])]
    assert plan_indexes(existing, [SPEC])[0].kind == "conflict"


def test_ttl_change_is_updated_in_place():
    spec = IndexSpec("ttl", (("captured_at", 1),), ttl_seconds=60)
    existing = [info("ttl", [("captured_at", 1)], expireAfterSeconds=30)]
    action = plan_indexes(existing, [spec])[0]
    assert (action.kind, action.detail) == ("ttl", "ttl")


def test_empty_desired_plans_nothing():
    assert plan_indexes([info("x", [("a", 1)])], []) == []


def test_is_subset_ignores_server_defaults():
    desired = {"mappings": {"dynamic": False, "fields": {"a": {"type": "token"}}}}
    actual = {
        "analyzer": "lucene.standard",
        "mappings": {"dynamic": False, "fields": {"a": {"type": "token", "norms": "omit"}}},
    }
    assert is_subset(desired, actual)
    assert not is_subset({"fields": [{"path": "a"}]}, {"fields": [{"path": "b"}]})
    assert not is_subset({"fields": [1, 2]}, {"fields": [1]})
