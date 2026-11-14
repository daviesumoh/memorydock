from datetime import UTC, datetime

import atlas_setup
import pytest
from pymongo.errors import DuplicateKeyError, WriteError

NOW = datetime.now(UTC).replace(microsecond=0)
HASH = "sha256:" + "a" * 64


def memory(_id: str, **overrides):
    doc = {
        "_id": _id,
        "tenant_id": "halcyon",
        "scope_key": "project:halcyon/lantern",
        "scope_level": "project",
        "type": "decision",
        "status": "active",
        "category": "product",
        "content": "Onboarding must take under 3 minutes.",
        "embed_text": "Onboarding under 3 minutes",
        "entities": [],
        "inject_in_work": True,
        "instruction_like": False,
        "sensitivity": {},
        "provenance": {
            "source_client": "chatgpt",
            "captured_by": "extension",
            "actor_user": "usr_1",
            "turn_ids": [],
        },
        "trust": {"asserted_by": "extracted_user", "confidence": 0.85, "flags": 0},
        "validity": {"valid_from": NOW, "expires_at": None},
        "version": 1,
        "content_hash": HASH,
        "forgotten": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def db(admin_client, test_db_name):
    assert atlas_setup.main(["--db", test_db_name]) == 0
    return admin_client[test_db_name]


def test_second_run_changes_nothing(db, test_db_name, capsys):
    capsys.readouterr()
    assert atlas_setup.main(["--db", test_db_name]) == 0
    lines = capsys.readouterr().out.splitlines()[1:]
    changes = [line for line in lines if not line.startswith(("ok ", "create search index"))]
    assert changes == [], changes


def test_valid_memory_is_accepted(db):
    db.memories.insert_one(memory("mem_1"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"_id": "nope_1"},
        {"status": "deleted"},
        {"scope_key": "global"},
        {"trust": {"asserted_by": "agent_inferred", "confidence": 1.5, "flags": 0}},
        {"content_hash": "md5:abc"},
        {"status": "forgotten"},  # forgotten with content still present
    ],
)
def test_invalid_memory_is_rejected(db, overrides):
    with pytest.raises(WriteError) as exc:
        db.memories.insert_one(memory("mem_2", **overrides))
    assert exc.value.code == 121


def test_forgotten_memory_with_content_purged_is_accepted(db):
    db.memories.insert_one(
        memory(
            "mem_3",
            status="forgotten",
            content=None,
            embed_text=None,
            entities=None,
            forgotten={"by": "usr_1", "at": NOW, "reason": "wrong"},
        )
    )


def test_one_live_memory_per_content_hash_and_scope(db):
    db.memories.insert_one(memory("mem_4"))
    with pytest.raises(DuplicateKeyError):
        db.memories.insert_one(memory("mem_5"))
    db.memories.insert_one(memory("mem_6", status="superseded"))


def test_users_pre_created_without_idp_sub_do_not_collide(db):
    base = {
        "tenant_id": "halcyon",
        "teams": [],
        "roles": ["member"],
        "idp_sub": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    db.users.insert_one({"_id": "usr_a", "email": "rosa@example.com", **base})
    db.users.insert_one({"_id": "usr_b", "email": "milo@example.com", **base})
