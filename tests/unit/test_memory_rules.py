from datetime import UTC, datetime, timedelta

import pytest
from memorydock_core.errors import InvalidInput
from memorydock_core.memory import service, text
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_core.scope import allowed_scopes

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def principal(*, projects=("lantern",), teams=("product",), client="claude-code", status="active"):
    refs = tuple(ProjectRef(f"prj_{s}", s, s.title(), False) for s in projects)
    user = UserIdentity(
        tenant_id="halcyon",
        user_id="usr_rosa",
        email="rosa@example.com",
        display_name="Rosa",
        roles=("member",),
        teams=tuple(teams),
        projects=refs,
        scopes=allowed_scopes("halcyon", "usr_rosa", projects=projects, teams=teams),
    )
    return Principal(user, "ses_rosa", status, client, "client", False)


def test_hash_ignores_case_spacing_and_unicode_forms():
    a = text.content_hash("Onboarding  must finish\nin under 3 minutes")
    b = text.content_hash("  onboarding must FINISH in under 3 minutes ")
    assert a == b
    assert text.content_hash("ﬁle") == text.content_hash("file")
    assert a != text.content_hash("Onboarding must finish in under 4 minutes")
    assert a.startswith("sha256:") and len(a) == 7 + 64


def test_embed_text_is_capped():
    assert len(text.embed_text("x" * 5000)) == text.EMBED_TEXT_MAX
    assert text.embed_text("  short  ") == "short"


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (None, "user:halcyon/usr_rosa"),
        ("user", "user:halcyon/usr_rosa"),
        ("project", "project:halcyon/lantern"),
        ("team", "team:halcyon/product"),
        ("org", "org:halcyon"),
    ],
)
def test_scope_resolves_to_the_one_scope_of_that_level(level, expected):
    assert service.resolve_scope(principal(), level) == expected


def test_scope_with_no_or_several_candidates_is_refused():
    with pytest.raises(InvalidInput) as none:
        service.resolve_scope(principal(projects=()), "project")
    assert none.value.code == "no_scope"
    with pytest.raises(InvalidInput) as many:
        service.resolve_scope(principal(projects=("lantern", "beacon")), "project")
    assert many.value.code == "scope_ambiguous"
    with pytest.raises(InvalidInput):
        service.resolve_scope(principal(teams=()), "team")


@pytest.mark.parametrize(
    ("client", "stated", "expected"),
    [
        ("claude-code", True, "user_confirmed"),
        ("claude-code", False, "agent_inferred"),
        ("chatgpt", True, "user_confirmed"),
        ("console", False, "user_stated"),
    ],
)
def test_trust_comes_from_the_caller_not_the_body(client, stated, expected):
    assert service.derive_trust(principal(client=client), stated_by_user=stated) == expected


def test_an_agent_session_never_produces_user_stated():
    for client in ("claude-code", "codex", "claude-app", "chatgpt", "other"):
        for stated in (True, False):
            p = principal(client=client)
            assert service.derive_trust(p, stated_by_user=stated) != "user_stated"


def make(content="Use Postgres 16", type="fact", entities=None):
    p = principal()
    return service.new_memory(
        p,
        content=content,
        type=type,
        scope_key="project:halcyon/lantern",
        trust="user_confirmed",
        entities=entities,
        captured_by="mcp_tool",
        now=NOW,
    )


def test_new_memory_shape():
    m = make()
    assert m["_id"].startswith("mem_")
    assert m["scope_level"] == "project"
    assert m["status"] == "active" and m["version"] == 1
    assert m["trust"] == {"asserted_by": "user_confirmed", "confidence": 0.95, "flags": 0}
    assert m["provenance"]["actor_user"] == "usr_rosa"
    assert m["provenance"]["session_id"] == "ses_rosa"
    assert m["content_hash"] == text.content_hash("Use Postgres 16")
    assert m["validity"] == {"valid_from": NOW, "expires_at": None}


@pytest.mark.parametrize(("type", "days"), [("open_question", 14), ("episode", 30)])
def test_short_lived_types_expire(type, days):
    assert make(type=type)["validity"]["expires_at"] == NOW + timedelta(days=days)


def test_entities_are_trimmed_and_deduplicated():
    m = make(entities=["Lantern", " lantern ", "Rosa  Diaz", "   "])
    assert m["entities"] == [
        {"name": "Lantern", "kind": "topic"},
        {"name": "Rosa Diaz", "kind": "topic"},
    ]
    with pytest.raises(InvalidInput):
        make(entities=[f"e{i}" for i in range(21)])
