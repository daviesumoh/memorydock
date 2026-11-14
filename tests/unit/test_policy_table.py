"""Decision table for the Cedar bundle in policies/. Expected results come from the policy rules,
not from running the engine: each case says what must happen and which policy decides it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from memorydock_core.policy import entities as E
from memorydock_core.policy.bundle import Bundle, InvalidBundle, load_dir, policy_ids, validate
from memorydock_core.policy.pdp import PDP, Request, uid

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = load_dir(ROOT / "policies")

H, N, F = "halcyon", "northwind", "frozen"
LANTERN = f"project:{H}/lantern"


def scopes(tenant: str, user: str, *, project: bool = True) -> list[str]:
    out = [f"user:{tenant}/{user}", f"team:{tenant}/product", f"org:{tenant}"]
    return out + ([f"project:{tenant}/lantern"] if project else [])


def mem(mid: str, scope_key: str, *, status="active", owner="usr_rosa", cap="org", confined=False):
    return E.memory(mid, scope_key=scope_key, status=status, asserted_by="extracted_user",
                    owner_user=owner, category_max_scope=cap, confined=confined)  # fmt: skip


WORLD = [
    E.org(H, kill_switch=False),
    E.org(N, kill_switch=False),
    E.org(F, kill_switch=True),
    E.team(H, "product"),
    E.user("usr_rosa", H, readable=scopes(H, "usr_rosa"), writable=scopes(H, "usr_rosa"),
           is_admin=False, teams=["product"]),
    E.user("usr_milo", H, readable=scopes(H, "usr_milo"), writable=scopes(H, "usr_milo"), is_admin=True),
    E.user("usr_otto", H, readable=scopes(H, "usr_otto", project=False),
           writable=scopes(H, "usr_otto", project=False), is_admin=False),
    E.user("usr_ivy", N, readable=scopes(N, "usr_ivy"), writable=scopes(N, "usr_ivy"), is_admin=True),
    E.user("usr_frank", F, readable=scopes(F, "usr_frank"), writable=scopes(F, "usr_frank"), is_admin=True),
    E.session("ses_rosa", H, user_id="usr_rosa", client="claude-code", status="active"),
    E.session("ses_rosa_paused", H, user_id="usr_rosa", client="claude-code", status="paused"),
    E.session("ses_rosa_revoked", H, user_id="usr_rosa", client="codex", status="revoked"),
    E.session("ses_rosa_ended", H, user_id="usr_rosa", client="codex", status="ended"),
    E.session("ses_milo", H, user_id="usr_milo", client="console", status="active"),
    E.session("ses_otto", H, user_id="usr_otto", client="claude-app", status="active"),
    E.session("ses_ivy", N, user_id="usr_ivy", client="chatgpt", status="active"),
    E.session("ses_frank", F, user_id="usr_frank", client="claude-code", status="active"),
    E.project("prj_lantern", H, "lantern", members=["usr_rosa", "usr_milo"], maintainers=["usr_milo"]),
    mem("mem_proj", LANTERN),
    mem("mem_prop", LANTERN, status="proposed"),
    mem("mem_rosa", f"user:{H}/usr_rosa"),
    mem("mem_milo", f"user:{H}/usr_milo", owner="usr_milo"),
    mem("mem_org", f"org:{H}"),
    mem("mem_team", f"team:{H}/product"),
    mem("mem_conf", f"user:{H}/usr_rosa", cap="user", confined=True),
    mem("mem_conf_proj", LANTERN, cap="user", confined=True),
    mem("mem_capped", LANTERN, cap="user"),
    mem("mem_cap_team", f"user:{H}/usr_rosa", cap="team"),
    mem("mem_ivy", f"org:{N}", owner="usr_ivy"),
    mem("mem_frank", f"org:{F}", owner="usr_frank"),
    E.review_item("rev_rosa", owner_user="usr_rosa"),
    E.review_item("rev_milo", owner_user="usr_milo"),
    E.approval("apr_rosa", H, requester="usr_rosa", approvers=["usr_milo"]),
    E.approval("apr_milo", H, requester="usr_milo", approvers=["usr_milo"]),
    E.repo_path("path_ok", project_id="prj_lantern", path="src/app.py", lease_conflict=False),
    E.repo_path("path_busy", project_id="prj_lantern", path="src/auth.py", lease_conflict=True),
    E.lease("lease_1", project_id="prj_lantern", holder="usr_milo", resource_kind="repo_path"),
    E.task("task_1", project_id="prj_lantern", owner="usr_rosa"),
    E.external_target("ext_branch", system="github", kind="branch", project_id="prj_lantern", protected=False),
    E.external_target("ext_pr", system="github", kind="pull_request", project_id="prj_lantern", protected=False),
    E.external_target("ext_main", system="github", kind="pull_request", project_id="prj_lantern", protected=True),
    E.audit_view(H),
    E.audit_view(N),
]  # fmt: skip

KIND = {"ses": "AgentSession", "mem": "Memory", "rev": "ReviewItem", "apr": "Approval",
        "path": "RepoPath", "lease": "Lease", "task": "Task", "ext": "ExternalTarget"}  # fmt: skip


def resource(rid: str) -> str:
    if rid.startswith("audit:"):
        return uid("AuditView", rid.removeprefix("audit:"))
    return uid(KIND[rid.split("_", 1)[0]], rid)


ORG_SHARE = {"targetLevel": "org", "targetRank": 3, "targetScopeKey": f"org:{H}"}
TEAM_SHARE = {"targetLevel": "team", "targetRank": 2, "targetScopeKey": f"team:{H}/product"}
PROJ_SHARE = {"targetLevel": "project", "targetRank": 1, "targetScopeKey": LANTERN}
REASON = {"reason": "wrong"}

# (case id, session, action, resource, context, expected effect, policy id that must be reported)
Case = tuple[str, str, str, str, dict[str, Any], str, str | None]
CASES: list[Case] = [
    # memory reads
    ("read own project memory", "ses_rosa", "memory.read", "mem_proj", {}, "allow", "memory-read-in-scope"),
    ("read own personal memory", "ses_rosa", "memory.read", "mem_rosa", {}, "allow", "memory-read-in-scope"),
    ("read org memory", "ses_rosa", "memory.read", "mem_org", {}, "allow", None),
    ("read team memory", "ses_rosa", "memory.read", "mem_team", {}, "allow", None),
    ("read another user's personal memory", "ses_rosa", "memory.read", "mem_milo", {}, "deny", None),
    ("admin can't read members' personal memory", "ses_milo", "memory.read", "mem_rosa", {}, "deny", None),
    ("proposed memories are never recallable", "ses_rosa", "memory.read", "mem_prop", {}, "deny", None),
    ("non-member can't read project memory", "ses_otto", "memory.read", "mem_proj", {}, "deny", None),
    ("non-member reads org memory", "ses_otto", "memory.read", "mem_org", {}, "allow", None),
    ("cross-tenant read denied", "ses_ivy", "memory.read", "mem_proj", {}, "deny", None),
    ("cross-tenant read of org memory denied", "ses_rosa", "memory.read", "mem_ivy", {}, "deny", None),
    ("paused session can still read", "ses_rosa_paused", "memory.read", "mem_proj", {}, "allow", None),
    ("revoked session can't read", "ses_rosa_revoked", "memory.read", "mem_proj", {}, "deny", "session-not-live"),
    ("ended session can't read", "ses_rosa_ended", "memory.read", "mem_proj", {}, "deny", "session-not-live"),
    ("kill switch blocks reads", "ses_frank", "memory.read", "mem_frank", {}, "deny", "org-kill-switch"),
    # memory writes
    ("write in project scope", "ses_rosa", "memory.write", "mem_proj", {}, "allow", "memory-write-in-scope"),
    ("write personal memory", "ses_rosa", "memory.write", "mem_rosa", {}, "allow", None),
    ("write into another user's scope", "ses_rosa", "memory.write", "mem_milo", {}, "deny", None),
    ("non-member writes project scope", "ses_otto", "memory.write", "mem_proj", {}, "deny", None),
    ("cross-tenant write denied", "ses_ivy", "memory.write", "mem_proj", {}, "deny", None),
    ("paused session can't write", "ses_rosa_paused", "memory.write", "mem_proj", {}, "deny", "session-not-active-no-writes"),
    ("revoked session can't write", "ses_rosa_revoked", "memory.write", "mem_rosa", {}, "deny", "session-not-live"),
    ("kill switch blocks writes", "ses_frank", "memory.write", "mem_frank", {}, "deny", "org-kill-switch"),
    ("org write needs approval", "ses_rosa", "memory.write", "mem_org", {}, "approval_required", "approve-org-write"),
    ("team write needs no approval", "ses_rosa", "memory.write", "mem_team", {}, "allow", None),
    ("confined category stays personal", "ses_rosa", "memory.write", "mem_conf", {}, "allow", None),
    ("confined category can't be written to a project", "ses_rosa", "memory.write", "mem_conf_proj", {}, "deny", "category-confined-to-personal"),
    ("category cap blocks project scope", "ses_rosa", "memory.write", "mem_capped", {}, "deny", "category-max-scope"),
    # correct, flag, forget
    ("correct in scope", "ses_rosa", "memory.correct", "mem_proj", {}, "allow", None),
    ("correct out of scope", "ses_otto", "memory.correct", "mem_proj", {}, "deny", None),
    ("flag in scope", "ses_rosa", "memory.flag", "mem_org", {}, "allow", None),
    ("paused session can't flag", "ses_rosa_paused", "memory.flag", "mem_org", {}, "deny", "session-not-active-no-writes"),
    ("forget personal memory without reason", "ses_rosa", "memory.forget", "mem_rosa", {}, "allow", None),
    ("forget shared memory needs a reason", "ses_rosa", "memory.forget", "mem_proj", {}, "deny", "shared-forget-needs-reason"),
    ("forget shared memory with empty reason", "ses_rosa", "memory.forget", "mem_proj", {"reason": ""}, "deny", "shared-forget-needs-reason"),
    ("forget shared memory with reason", "ses_rosa", "memory.forget", "mem_proj", REASON, "allow", None),
    ("forget another user's memory", "ses_rosa", "memory.forget", "mem_milo", REASON, "deny", None),
    # share
    ("share personal to project", "ses_rosa", "memory.share", "mem_rosa", PROJ_SHARE, "allow", None),
    ("share personal to org needs approval", "ses_rosa", "memory.share", "mem_rosa", ORG_SHARE, "approval_required", "approve-org-share"),
    ("share without a target", "ses_rosa", "memory.share", "mem_rosa", {}, "deny", "share-target-in-scope"),
    ("share into a scope the user can't write", "ses_otto", "memory.share", "mem_org",
     {"targetLevel": "project", "targetRank": 1, "targetScopeKey": LANTERN}, "deny", "share-target-in-scope"),
    ("share confined memory out of personal", "ses_rosa", "memory.share", "mem_conf", PROJ_SHARE, "deny", "category-confined-to-personal"),
    ("share above category cap", "ses_rosa", "memory.share", "mem_cap_team", ORG_SHARE, "deny", "category-max-scope"),
    ("share up to category cap", "ses_rosa", "memory.share", "mem_cap_team", TEAM_SHARE, "allow", None),
    # capture
    ("capture into own session", "ses_rosa", "turn.capture", "ses_rosa", {}, "allow", "capture-own-session"),
    ("capture into another session", "ses_rosa", "turn.capture", "ses_milo", {}, "deny", None),
    ("paused session can't capture", "ses_rosa_paused", "turn.capture", "ses_rosa_paused", {}, "deny", "session-not-active-no-writes"),
    # review items
    ("read own review item", "ses_rosa", "review.read", "rev_rosa", {}, "allow", "review-own-items"),
    ("decide own review item", "ses_rosa", "review.decide", "rev_rosa", {}, "allow", None),
    ("decide someone else's review item", "ses_rosa", "review.decide", "rev_milo", {}, "deny", None),
    ("admin can't decide members' review items", "ses_milo", "review.decide", "rev_rosa", {}, "deny", None),
    # approvals
    ("approver decides", "ses_milo", "approval.decide", "apr_rosa", {}, "allow", "approver-decides"),
    ("requester can't decide own request", "ses_rosa", "approval.decide", "apr_rosa", {}, "deny", None),
    ("no self-approval even when listed", "ses_milo", "approval.decide", "apr_milo", {}, "deny", "no-self-approval"),
    ("requester reads own request", "ses_rosa", "approval.read", "apr_rosa", {}, "allow", "approval-read-involved"),
    ("uninvolved user can't read approval", "ses_otto", "approval.read", "apr_rosa", {}, "deny", None),
    ("paused approver can't decide", "ses_rosa_paused", "approval.decide", "apr_milo", {}, "deny", None),
    # files and leases
    ("member edits a free file", "ses_rosa", "file.edit", "path_ok", {}, "allow", "project-members-files"),
    ("edit blocked by another lease", "ses_rosa", "file.edit", "path_busy", {}, "deny", "file-edit-lease-conflict"),
    ("non-member can't edit", "ses_otto", "file.edit", "path_ok", {}, "deny", None),
    ("bash in project", "ses_rosa", "bash.exec", "path_busy", {}, "allow", None),
    ("acquire lease", "ses_rosa", "lease.acquire", "lease_1", {}, "allow", "project-members-leases"),
    ("override lease needs approval", "ses_rosa", "lease.override", "lease_1", {}, "approval_required", "approve-lease-override"),
    ("non-member can't read leases", "ses_otto", "lease.read", "lease_1", {}, "deny", None),
    ("paused session can read leases", "ses_rosa_paused", "lease.read", "lease_1", {}, "allow", None),
    # tasks
    ("member creates task", "ses_rosa", "task.create", "task_1", {}, "allow", "project-members-tasks"),
    ("member rolls back task", "ses_milo", "task.rollback", "task_1", {}, "allow", None),
    ("non-member can't claim task", "ses_otto", "task.claim", "task_1", {}, "deny", None),
    ("cross-tenant task read", "ses_ivy", "task.read", "task_1", {}, "deny", None),
    # external actions
    ("member creates branch", "ses_rosa", "github.create_branch", "ext_branch", {}, "allow", "project-members-external"),
    ("member opens PR", "ses_rosa", "github.open_pr", "ext_pr", {}, "allow", None),
    ("PR comment needs approval", "ses_rosa", "github.comment_pr", "ext_pr", {}, "approval_required", "approve-pr-comment"),
    ("non-maintainer can't merge", "ses_rosa", "github.merge_pr", "ext_pr", {}, "deny", "merge-needs-maintainer"),
    ("maintainer merges unprotected PR", "ses_milo", "github.merge_pr", "ext_pr", {}, "allow", None),
    ("protected merge needs approval", "ses_milo", "github.merge_pr", "ext_main", {}, "approval_required", "approve-protected-merge"),
    ("non-member can't act on GitHub", "ses_otto", "github.add_label", "ext_pr", {}, "deny", None),
    ("revoked session can't act on GitHub", "ses_rosa_revoked", "github.open_pr", "ext_pr", {}, "deny", "session-not-live"),
    # audit and policy views
    ("member reads own org audit", "ses_rosa", "audit.read", "audit:halcyon", {}, "allow", "audit-read-own-org"),
    ("member reads policies", "ses_otto", "policy.read", "audit:halcyon", {}, "allow", None),
    ("cross-tenant audit read", "ses_ivy", "audit.read", "audit:halcyon", {}, "deny", None),
    ("member can't verify chain", "ses_rosa", "audit.verify", "audit:halcyon", {}, "deny", None),
    ("admin verifies chain", "ses_milo", "audit.verify", "audit:halcyon", {}, "allow", "audit-admin-verify"),
    ("admin of another org can't verify", "ses_ivy", "audit.verify", "audit:halcyon", {}, "deny", None),
    # session control
    ("owner pauses own session", "ses_rosa", "session.pause", "ses_rosa_paused", {}, "allow", "session-control-owner-or-admin"),
    ("admin revokes member session", "ses_milo", "session.revoke", "ses_rosa", {}, "allow", None),
    ("member can't revoke others", "ses_rosa", "session.revoke", "ses_milo", {}, "deny", None),
    ("other-tenant admin can't revoke", "ses_ivy", "session.revoke", "ses_rosa", {}, "deny", None),
    ("paused session can't pause others", "ses_rosa_paused", "session.pause", "ses_rosa", {}, "deny", None),
]  # fmt: skip


@pytest.fixture(scope="module")
def pdp() -> PDP:
    return PDP(BUNDLE)


def test_table_has_enough_cases():
    assert len(CASES) >= 60


@pytest.mark.parametrize(
    ("name", "session", "action", "res", "ctx", "effect", "policy"),
    CASES,
    ids=[c[0] for c in CASES],
)
def test_decision(pdp, name, session, action, res, ctx, effect, policy):  # fmt: skip
    decision = pdp.authorize(
        Request(uid("AgentSession", session), action, resource(res), ctx), WORLD
    )
    assert decision.effect == effect, decision.reason
    assert decision.policy_version == BUNDLE.version
    assert all(not p.startswith("policy") for p in decision.policy_ids), "positional ids leaked"
    if policy is not None:
        assert policy in decision.policy_ids


def test_default_deny_reports_no_policy(pdp):
    d = pdp.authorize(
        Request(uid("AgentSession", "ses_rosa"), "memory.read", resource("mem_milo"), {}), WORLD
    )
    assert d.effect == "deny" and d.policy_ids == () and d.reason == "no policy permits this"


def test_every_forbid_is_exercised_by_the_table():
    forbids = {i for i in policy_ids(BUNDLE.authz_text) if i}
    permits_only = {
        "memory-read-in-scope", "memory-write-in-scope", "capture-own-session", "review-own-items",
        "approver-decides", "approval-read-involved", "project-members-files", "project-members-leases",
        "project-members-tasks", "project-members-external", "audit-read-own-org", "audit-admin-verify",
        "session-control-owner-or-admin",
    }  # fmt: skip
    assert forbids - permits_only <= {c[6] for c in CASES}


def test_unknown_action_denies(pdp):
    d = pdp.authorize(
        Request(uid("AgentSession", "ses_rosa"), "memory.delete_all", resource("mem_proj"), {}),
        WORLD,
    )
    assert d.effect == "deny"


def test_missing_entity_fails_closed(pdp):
    world = [e for e in WORLD if e["uid"]["id"] != "usr_rosa"]
    d = pdp.authorize(
        Request(uid("AgentSession", "ses_rosa"), "memory.read", resource("mem_proj"), {}), world
    )
    assert d.effect == "deny"


def test_batch_matches_single(pdp):
    reqs = [
        Request(uid("AgentSession", s), a, resource(r), c) for _, s, a, r, c, _, _ in CASES[:20]
    ]
    assert [d.effect for d in pdp.authorize_batch(reqs, WORLD)] == [c[5] for c in CASES[:20]]


def test_entity_ids_with_quotes_are_refused():
    with pytest.raises(ValueError):
        uid("Memory", 'mem_1" || true')


# Bundle validation


def test_repo_bundle_is_valid():
    assert validate(BUNDLE) == []


def test_version_is_stable_and_tracks_content():
    assert BUNDLE.version == load_dir(ROOT / "policies").version
    changed = Bundle(BUNDLE.schema_text, BUNDLE.authz_text + "\n", BUNDLE.approvals_text)
    assert changed.version != BUNDLE.version
    assert len(BUNDLE.version) == 12 and BUNDLE.content_hash.startswith("sha256:")


def test_moving_text_between_files_changes_version():
    a = Bundle("s", "ab", "c")
    b = Bundle("s", "a", "bc")
    assert a.version != b.version


@pytest.mark.parametrize(
    ("authz", "problem"),
    [
        ("permit (principal, action, resource);", "without @id"),
        ('@id("x") permit (principal, action, resource);\n@id("x") forbid (principal, action, resource);', "duplicate @id"),
        ('@id("x") permit (principal, action, resource) when { resource.nope };', "schema validation"),
        ("this is not cedar", "does not parse"),
        ("", "no policies"),
    ],
)  # fmt: skip
def test_bad_bundles_are_rejected(authz, problem):
    bad = Bundle(BUNDLE.schema_text, authz, BUNDLE.approvals_text)
    problems = validate(bad)
    assert any(problem in p for p in problems), problems
    with pytest.raises(InvalidBundle):
        PDP(bad)
