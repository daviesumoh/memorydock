import pytest
from atlas_roles import (
    desired_privileges,
    diff,
    parse_role,
    resolve_databases,
)

COLLS = ["audit_log", "memories", "orgs", "policy_heads", "turns", "checkpoints"]
DBS = ["memorydock", "memorydock_dev_a"]


def actions(privs, db, coll):
    return {a for a, d, c in privs if d == db and c == coll}


def test_gateway_gets_crud_everywhere_but_audit_log_is_append_only():
    privs = desired_privileges("md_gateway_role", COLLS, DBS)
    for db in DBS:
        assert actions(privs, db, "orgs") == {"FIND", "INSERT", "UPDATE", "REMOVE"}
        assert actions(privs, db, "audit_log") == {"FIND", "INSERT", "CHANGE_STREAM"}


def test_change_streams_only_where_listed():
    gw = desired_privileges("md_gateway_role", COLLS, DBS)
    wk = desired_privileges("md_worker_role", COLLS, DBS)
    assert "CHANGE_STREAM" in actions(gw, "memorydock", "memories")
    assert "CHANGE_STREAM" not in actions(gw, "memorydock", "orgs")
    assert "CHANGE_STREAM" not in actions(gw, "memorydock", "turns")
    assert "CHANGE_STREAM" in actions(wk, "memorydock", "turns")


def test_checkpoints_are_worker_only():
    gw = desired_privileges("md_gateway_role", COLLS, DBS)
    wk = desired_privileges("md_worker_role", COLLS, DBS)
    assert actions(gw, "memorydock", "checkpoints") == set()
    assert actions(wk, "memorydock", "checkpoints") == {"FIND", "INSERT", "UPDATE", "REMOVE"}


def test_no_admin_actions_ever():
    allowed = {"FIND", "INSERT", "UPDATE", "REMOVE", "CHANGE_STREAM"}
    for role in ("md_gateway_role", "md_worker_role"):
        assert {a for a, _, _ in desired_privileges(role, COLLS, DBS)} <= allowed


def test_every_database_gets_the_same_grants():
    privs = desired_privileges("md_worker_role", COLLS, DBS)
    per_db = [{(a, c) for a, d, c in privs if d == db} for db in DBS]
    assert per_db[0] == per_db[1]


def test_empty_inputs_give_empty_set():
    assert desired_privileges("md_gateway_role", [], DBS) == set()
    assert desired_privileges("md_gateway_role", COLLS, []) == set()


def test_existing_databases_are_kept():
    current = {("FIND", "memorydock_dev_b", "orgs")}
    assert resolve_databases(current, ["memorydock_dev_a"], []) == [
        "memorydock",
        "memorydock_dev_a",
        "memorydock_dev_b",
    ]


def test_remove_db_and_refuse_shared_or_foreign():
    current = {("FIND", "memorydock_dev_b", "orgs")}
    assert resolve_databases(current, [], ["memorydock_dev_b"]) == ["memorydock"]
    with pytest.raises(ValueError):
        resolve_databases(current, [], ["memorydock"])
    with pytest.raises(ValueError):
        resolve_databases(set(), ["admin"], [])


def test_parse_role_and_diff():
    doc = {
        "actions": [
            {"action": "FIND", "resources": [{"db": "memorydock", "collection": "orgs"}]},
            {
                "action": "DROP_COLLECTION",
                "resources": [{"db": "memorydock", "collection": "orgs"}],
            },
        ]
    }
    current = parse_role(doc)
    desired = {("FIND", "memorydock", "orgs"), ("INSERT", "memorydock", "orgs")}
    assert diff(current, desired) == [
        "  + INSERT on memorydock.orgs",
        "  - DROP_COLLECTION on memorydock.orgs",
    ]
    assert diff(desired, desired) == []
