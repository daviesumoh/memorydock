from datetime import UTC, datetime

import pytest
from memorydock_core.errors import InvalidInput
from memorydock_core.leases.service import held_message, normalize_path, normalize_repo


@pytest.mark.parametrize("remote", [
    "github.com/Halcyon/Lantern",
    "https://github.com/halcyon/lantern.git",
    "https://github.com/halcyon/lantern/",
    "git@github.com:halcyon/lantern.git",
    "ssh://git@github.com/halcyon/lantern.git",
    "ssh://git@github.com:22/halcyon/lantern",
])  # fmt: skip
def test_remote_forms_normalize_to_one_id(remote):
    assert normalize_repo(remote) == "github.com/halcyon/lantern"


@pytest.mark.parametrize("remote", ["", "lantern", "github.com/halcyon", "/tmp/lantern"])
def test_other_remotes_map_to_nothing(remote):
    assert normalize_repo(remote) is None


@pytest.mark.parametrize(("path", "clean"), [
    ("src/auth/middleware.ts", "src/auth/middleware.ts"),
    ("./src//auth/./middleware.ts", "src/auth/middleware.ts"),
    ("src\\auth\\middleware.ts", "src/auth/middleware.ts"),
    ("docs/../README.md", "README.md"),
])  # fmt: skip
def test_paths_normalize(path, clean):
    assert normalize_path(path) == clean


@pytest.mark.parametrize(
    "path", ["", "  ", "/etc/passwd", "..", "../other/repo.py", "a/../../x", "."]
)
def test_paths_outside_the_repo_are_refused(path):
    with pytest.raises(InvalidInput):
        normalize_path(path)


def lease(state="editing", intent="add rate limiting", name="Rosa"):
    return {
        "details": {"repo_id": "github.com/halcyon/lantern", "path": "src/auth/middleware.ts"},
        "holder": {"user_id": "usr_rosa", "client": "claude-code", "display_name": name},
        "intent": intent, "state": state, "fence": 17,
        "created_at": datetime(2026, 11, 14, 10, 42, tzinfo=UTC),
    }  # fmt: skip


def test_held_message_says_who_what_since_and_options():
    msg = held_message(lease())
    assert msg == (
        "memorydock: src/auth/middleware.ts is being edited by Rosa (Claude Code) for "
        "'add rate limiting' since 10:42 UTC (fence 17). Don't edit it. Options: (1) work on "
        "other files, (2) try again later, (3) ask Rosa to release it."
    )
    assert "for '" not in held_message(lease(intent=None))
    assert "usr_rosa" in held_message(lease(name=None))
    assert "waiting to merge" in held_message(lease(state="pending_merge"))
