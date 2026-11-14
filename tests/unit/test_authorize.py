"""authorize() against the repository's policy bundle, with entities built from a Principal."""

from __future__ import annotations

from pathlib import Path

import pytest
from memorydock_core.policy import entities as E
from memorydock_core.policy.authorize import authorize, principal_entities
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP, uid
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_core.scope import allowed_scopes

ROOT = Path(__file__).resolve().parents[2]
H = "halcyon"


def principal(*, roles=("member",), status="active", kill_switch=False, tenant=H) -> Principal:
    projects = (ProjectRef(project_id="prj_lantern", slug="lantern", name="L", maintainer=False),)
    user = UserIdentity(
        tenant_id=tenant,
        user_id="usr_rosa",
        email="rosa@example.com",
        display_name=None,
        roles=roles,
        teams=("product",),
        projects=projects,
        scopes=allowed_scopes(tenant, "usr_rosa", projects=["lantern"], teams=["product"]),
    )
    return Principal(
        user=user,
        session_id="ses_rosa",
        session_status=status,
        client="console",
        client_id="client_console",
        kill_switch=kill_switch,
    )


@pytest.fixture(scope="module")
def pdp() -> PDP:
    return PDP(load_dir(ROOT / "policies"))


def read_audit(pdp: PDP, p: Principal, org: str = H):
    return authorize(pdp, p, "audit.read", uid("AuditView", org), [E.audit_view(org)])


def test_members_read_their_own_orgs_audit(pdp):
    decision = read_audit(pdp, principal())
    assert decision.allowed
    assert decision.policy_ids == ("audit-read-own-org",)


def test_another_orgs_audit_is_denied(pdp):
    assert not read_audit(pdp, principal(), org="northwind").allowed


def test_only_admins_verify_the_chain(pdp):
    def verify(p):
        return authorize(pdp, p, "audit.verify", uid("AuditView", H), [E.audit_view(H)])

    assert not verify(principal()).allowed
    assert verify(principal(roles=("admin", "member"))).allowed


@pytest.mark.parametrize(
    ("p", "policy"),
    [
        (principal(kill_switch=True), "org-kill-switch"),
        (principal(status="revoked"), "session-not-live"),
        (principal(status="ended"), "session-not-live"),
    ],
)
def test_kill_switch_and_dead_sessions_deny_reads(pdp, p, policy):
    decision = read_audit(pdp, p)
    assert decision.effect == "deny"
    assert policy in decision.policy_ids


def test_a_paused_session_still_reads(pdp):
    assert read_audit(pdp, principal(status="paused")).allowed


def test_reads_memory_only_in_the_principals_scopes(pdp):
    def read(scope_key):
        mem = E.memory(
            "mem_1",
            scope_key=scope_key,
            status="active",
            asserted_by="user",
            owner_user="usr_rosa",
            category_max_scope="org",
            confined=False,
        )
        return authorize(pdp, principal(), "memory.read", uid("Memory", "mem_1"), [mem])

    assert read(f"project:{H}/lantern").allowed
    assert read(f"team:{H}/product").allowed
    assert not read(f"project:{H}/other").allowed
    assert not read("org:northwind").allowed


def test_a_missing_resource_entity_fails_closed(pdp):
    p = principal()
    assert not authorize(pdp, p, "audit.read", uid("AuditView", H)).allowed


def test_principal_entities_carry_teams_and_admin_flag():
    p = principal(roles=("admin",))
    by_type = {e["uid"]["type"].split("::")[-1]: e for e in principal_entities(p)}
    assert set(by_type) == {"Org", "Team", "User", "AgentSession"}
    assert by_type["User"]["attrs"]["isOrgAdmin"] is True
    assert {"type": "Memorydock::Team", "id": f"{H}/product"} in by_type["User"]["parents"]
