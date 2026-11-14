from datetime import UTC, datetime, timedelta, timezone

import pytest
from memorydock_core.audit.chain import GENESIS, canonical, entry_hash, iso_ms, truncate_ms
from memorydock_core.audit.events import Actor, AuditEvent, DecisionRecord, Resource, Result
from memorydock_core.audit.visibility import visibility
from pydantic import ValidationError

TS = datetime(2026, 11, 14, 12, 0, 0, 123456, tzinfo=UTC)


def test_truncate_to_milliseconds():
    assert truncate_ms(TS).microsecond == 123000


def test_iso_is_utc_with_milliseconds():
    assert iso_ms(TS) == "2026-11-14T12:00:00.123Z"
    est = TS.astimezone(timezone(timedelta(hours=-5)))
    assert iso_ms(est) == "2026-11-14T12:00:00.123Z"
    assert iso_ms(TS.replace(tzinfo=None)) == "2026-11-14T12:00:00.123Z"


def test_microseconds_below_a_millisecond_do_not_change_the_hash():
    # BSON keeps milliseconds only: a value read back must hash the same as the one written.
    a = {"ts": truncate_ms(TS), "seq": 1}
    b = {"ts": TS.replace(microsecond=123999), "seq": 1}
    assert entry_hash(GENESIS, a) == entry_hash(GENESIS, b)


def test_canonical_form_ignores_key_order_and_hash_field():
    assert canonical({"b": 1, "a": 2}) == canonical({"a": 2, "b": 1, "hash": "x"})
    assert canonical({"n": 1.0}) == canonical({"n": 1}) == b'{"n":1}'


def test_hash_chains_on_prev_hash_and_content():
    entry = {"seq": 1, "action": "memory.create"}
    h = entry_hash(GENESIS, entry)
    assert len(h) == 64 and h == entry_hash(GENESIS, entry)
    assert h != entry_hash("1" * 64, entry)
    assert h != entry_hash(GENESIS, {**entry, "action": "memory.forget"})


def test_events_refuse_unknown_fields_and_bad_actions():
    base = dict(
        actor=Actor(via="mcp"), action="memory.create", resource=Resource(type="memory"),
        decision=DecisionRecord(effect="allow"), result=Result(status="ok"),
    )  # fmt: skip
    AuditEvent(**base)
    with pytest.raises(ValidationError):
        AuditEvent(**{**base, "content": "secret"})
    with pytest.raises(ValidationError):
        AuditEvent(**{**base, "action": "DROP"})
    with pytest.raises(ValidationError):
        DecisionRecord(effect="allow", policy_version="nothex")


ROSA, MILO = "usr_rosa", "usr_milo"
READABLE = {"user:h/usr_rosa", "project:h/lantern", "org:h"}


def entry(user, keys):
    return {"actor": {"user_id": user}, "resource": {"scope_keys": keys}}


@pytest.mark.parametrize(
    ("e", "admin", "expected"),
    [
        (entry(ROSA, ["user:h/usr_rosa"]), False, "full"),
        (entry(MILO, ["project:h/lantern"]), False, "full"),
        (entry(MILO, ["org:h"]), False, "full"),
        (entry(MILO, ["user:h/usr_milo"]), False, "hidden"),
        (entry(MILO, ["project:h/secret"]), False, "hidden"),
        (entry(MILO, ["project:h/lantern", "user:h/usr_milo"]), False, "hidden"),
        (entry(MILO, []), False, "hidden"),
        (entry(MILO, ["user:h/usr_milo"]), True, "placeholder"),
        (entry(MILO, ["project:h/secret"]), True, "full"),
        (entry(None, []), True, "full"),
        ({}, False, "hidden"),
    ],
)
def test_visibility(e, admin, expected):
    assert (
        visibility(e, viewer_user_id=ROSA, readable_scopes=READABLE, is_org_admin=admin) == expected
    )
