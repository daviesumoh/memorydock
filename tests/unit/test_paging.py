import base64
import json

import pytest
from memorydock_core.errors import InvalidInput
from memorydock_core.ids import id_pattern, is_id, new_id
from memorydock_core.paging import decode_cursor, encode_cursor

MEM = id_pattern("mem")


def raw(doc) -> str:
    return base64.urlsafe_b64encode(json.dumps(doc).encode()).decode().rstrip("=")


def test_string_key_round_trips():
    key = new_id("mem")
    assert decode_cursor(encode_cursor(key), pattern=MEM) == key


@pytest.mark.parametrize("key", [0, 1, 2**40])
def test_integer_key_round_trips(key):
    assert decode_cursor(encode_cursor(key), integer=True) == key


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "!!!",
        "x" * 600,
        base64.urlsafe_b64encode(b"not json").decode(),
        raw([1, 2]),
        raw({"k": "mem_x"}),
        raw({"k": new_id("mem"), "v": 2}),
        raw({"k": new_id("mem"), "v": 1, "extra": 1}),
        raw({"k": new_id("aud"), "v": 1}),
        raw({"k": {"$gt": ""}, "v": 1}),
    ],
)
def test_malformed_string_cursor_is_rejected(cursor):
    with pytest.raises(InvalidInput) as exc:
        decode_cursor(cursor, pattern=MEM)
    assert exc.value.code == "invalid_cursor" and exc.value.field == "cursor"


@pytest.mark.parametrize("key", [True, -1, 1.5, "3"])
def test_malformed_integer_cursor_is_rejected(key):
    with pytest.raises(InvalidInput):
        decode_cursor(raw({"k": key, "v": 1}), integer=True)


def test_ids_have_prefix_and_ulid():
    value = new_id("mem")
    assert is_id(value, "mem") and not is_id(value, "aud")
    with pytest.raises(ValueError):
        new_id("nope")
