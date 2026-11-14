import pytest
from check_attribution import main, offending_lines


@pytest.mark.parametrize(
    "message",
    [
        "Add leases\n\nCo-authored-by: Someone <someone@example.com>",
        "Add leases\n\n\U0001f916 Generated with some tool",
        "Fix recall\n\nai-generated",
        "Fix recall, written by an AI",
        "Fix recall\nnoreply@anthropic.com",
    ],
)
def test_attribution_is_rejected(message):
    assert offending_lines(message)


def test_plain_message_passes():
    assert offending_lines("Reject memory writes whose scope_key comes from the body\n") == []


def test_git_comment_lines_are_ignored():
    assert offending_lines("Add x\n# Generated with git commit template\n") == []


def test_empty_message_passes():
    assert offending_lines("") == []


def test_main_reads_file(tmp_path):
    bad = tmp_path / "msg"
    bad.write_text("x\n\nCo-Authored-By: y\n")
    assert main(["prog", str(bad)]) == 1
    good = tmp_path / "ok"
    good.write_text("Add the audit chain verifier\n")
    assert main(["prog", str(good)]) == 0


def test_main_requires_one_argument():
    assert main(["prog"]) == 2
