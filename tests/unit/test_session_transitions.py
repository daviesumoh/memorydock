import itertools

from memorydock_core.sessions.service import TRANSITIONS

STATES = ("active", "paused", "revoked", "ended")
ALLOWED = {
    ("active", "paused"): "session.pause",
    ("paused", "active"): "session.resume",
    ("active", "revoked"): "session.revoke",
    ("paused", "revoked"): "session.revoke",
}


def test_every_cell_of_the_transition_table():
    for pair in itertools.product(STATES, STATES):
        assert TRANSITIONS.get(pair) == ALLOWED.get(pair), pair


def test_terminal_states_have_no_way_out():
    assert not [p for p in TRANSITIONS if p[0] in ("revoked", "ended")]
    assert not [p for p in TRANSITIONS if p[1] == "ended"]
