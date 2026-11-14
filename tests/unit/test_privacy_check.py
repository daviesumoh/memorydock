from pathlib import Path

import pytest
from privacy_check import REQUIRED_IGNORES, check_gitignore, check_text, run

FULL_GITIGNORE = "\n".join(REQUIRED_IGNORES) + "\n"


def kinds(findings):
    return [f.kind for f in findings]


def test_complete_gitignore_passes():
    assert check_gitignore(FULL_GITIGNORE, ["README.md", ".env.example"]) == []


def test_missing_ignore_pattern_is_reported():
    text = FULL_GITIGNORE.replace("BUILD_PROMPT.md\n", "")
    assert kinds(check_gitignore(text, [])) == ["missing ignore pattern 'BUILD_PROMPT.md'"]


def test_empty_gitignore_reports_every_pattern():
    assert len(check_gitignore("", [])) == len(REQUIRED_IGNORES)


@pytest.mark.parametrize("path", [".env", ".env.local", "console/.env.production"])
def test_tracked_env_file_is_reported(path):
    assert kinds(check_gitignore(FULL_GITIGNORE, [path])) == ["tracked env file"]


def test_empty_file_has_no_findings():
    assert check_text("docs/a.md", "", ["someone-unique"]) == []


@pytest.mark.parametrize(
    "line",
    ["see /Users/alice/repo", "cd /home/bob/work", r"C:\Users\carol\x", "open ~/Documents/x"],
)
def test_personal_paths_are_reported(line):
    assert kinds(check_text("docs/a.md", line, [])) == ["personal path"]


def test_placeholder_path_is_allowed():
    assert check_text("docs/a.md", "cd /path/to/repo && ls ~/.config", []) == []


@pytest.mark.parametrize(
    "email",
    [
        "you+rosa@example.com",
        "a@mail.example.org",
        "1+x@users.noreply.github.com",
        "git@github.com",
    ],
)
def test_allowed_emails_pass(email):
    assert check_text("docs/a.md", f"contact {email}", []) == []


def test_real_looking_email_is_reported():
    assert kinds(check_text("docs/a.md", "mail dev@gmail.com", [])) == ["email address"]


def test_package_version_is_not_an_email():
    assert check_text("docs/a.md", "npm i react@18.3.1 @scope/pkg", []) == []


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "0.0.0.0", "192.0.2.10", "198.51.100.7", "203.0.113.255"]
)
def test_allowed_ips_pass(ip):
    assert check_text("docs/a.md", f"host {ip}:8000", []) == []


@pytest.mark.parametrize("ip", ["10.0.0.4", "8.8.8.8", "192.0.3.1"])
def test_other_ips_are_reported(ip):
    assert kinds(check_text("docs/a.md", f"host {ip}.", [])) == ["ip address"]


def test_version_numbers_are_not_ips():
    assert check_text("docs/a.md", "uses 1.2.3.4.5 and v10.0.0.1 and 999.1.1.1", []) == []


@pytest.mark.parametrize(
    "line",
    [
        "# CRITICAL: do this",
        "IMPORTANT: read",
        "note to claude: x",
        "LLM Note - x",
        "Rule 12: never",
        "see \u00a74 for details",
        "as an AI model",
        "Generated with a tool",
        "Co-authored-by: someone",
    ],
)
def test_markers_are_reported(line):
    assert kinds(check_text("src/a.py", line, [])) == ["instruction or attribution marker"]


def test_product_names_are_not_markers():
    text = "Claude Code, Codex CLI, ChatGPT and the Claude app connect over MCP."
    assert check_text("README.md", text, []) == []


def test_identifier_match_is_case_insensitive():
    assert kinds(check_text("docs/a.md", "owner: Some-Handle", ["some-handle"])) == [
        "personal identifier"
    ]


def test_codeowners_may_name_handles():
    assert check_text(".github/CODEOWNERS", "* @some-handle", ["some-handle"]) == []


def test_findings_never_include_the_value():
    findings = check_text("docs/a.md", "mail dev@gmail.com from 8.8.8.8", ["secret-handle"])
    assert all("gmail" not in str(f) and "8.8.8.8" not in str(f) for f in findings)


def test_run_on_a_repo(tmp_path: Path, monkeypatch):
    import subprocess

    monkeypatch.setenv("CI", "1")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(FULL_GITIGNORE)
    (tmp_path / "ok.md").write_text("nothing personal here\n")
    (tmp_path / "bad.md").write_text("line one\nping 10.1.2.3\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert [str(f) for f in run(tmp_path)] == ["bad.md:2: ip address"]
