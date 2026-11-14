"""Fail if tracked files contain personal data, secrets or tool-attribution markers.

Output is file:line: kind. Matched values are never printed.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scan_secrets import scan as scan_secrets
from scan_secrets import tracked_files

REQUIRED_IGNORES = [
    ".env",
    ".env.*",
    "!.env.example",
    "*.pem",
    "*.key",
    "*.p12",
    "credentials*.json",
    "service-account*.json",
    ".netrc",
    "BUILD_PROMPT.md",
    "CLAUDE.md",
    ".claude/",
    ".codex/",
    ".local/",
    "*.private.md",
    ".venv/",
    "__pycache__/",
    "*.py[cod]",
    "*.egg-info/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".coverage",
    "htmlcov/",
    "dist/",
    "build/",
    "node_modules/",
    ".next/",
    "out/",
    "coverage/",
    "*.tsbuildinfo",
    "console/.env.local",
    "clients/extension/.env.local",
    "clients/extension/dist/",
    "playwright-report/",
    "test-results/",
    "playwright/.auth/",
    ".DS_Store",
    "Thumbs.db",
    "*.swp",
    "*~",
    ".idea/",
    ".vscode/*",
    "!.vscode/extensions.json",
]

# The checker and its tests have to spell out the patterns they look for.
PATTERN_SOURCES = {
    "scripts/privacy_check.py",
    "scripts/check_attribution.py",
    "tests/unit/test_privacy_check.py",
    "tests/unit/test_check_attribution.py",
}
# CODEOWNERS has to name GitHub handles.
IDENTIFIER_EXEMPT = {".github/CODEOWNERS"} | PATTERN_SOURCES

PERSONAL_PATH = re.compile(
    r"/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|[A-Za-z]:\\Users\\"
    r"|~/(?:Documents|Desktop|Downloads|Library|Pictures|Projects|code|src|dev)\b"
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "users.noreply.github.com")
ALLOWED_EMAILS = {"git@github.com"}
IPV4 = re.compile(r"(?<![\w.])((?:\d{1,3}\.){3}\d{1,3})(?!\.?\d)")
ALLOWED_IPS = {"127.0.0.1", "0.0.0.0"}
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
MARKERS = [
    re.compile(r"\bCRITICAL:"),
    re.compile(r"\bIMPORTANT:"),
    re.compile(r"(?i)NOTE TO (?:AI|CLAUDE|ASSISTANT)"),
    re.compile(r"(?i)LLM Note"),
    re.compile(r"\bRule \d+:"),
    re.compile("§\\d+"),
    re.compile(r"(?i)\bas an AI\b"),
    re.compile(r"(?i)Generated with"),
    re.compile(r"(?i)Co-authored-by"),
]
# .env keys whose values identify a person, an account or a cloud resource.
SENSITIVE_ENV_KEY = re.compile(
    r"(URI|KEY|SECRET|TOKEN|PASSWORD|_ID|DOMAIN|EMAIL|REPO|HOST|ACCOUNT|PROJECT)"
)
MIN_IDENTIFIER_LEN = 6


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}"


def check_gitignore(gitignore_text: str, tracked: list[str]) -> list[Finding]:
    present = {line.strip() for line in gitignore_text.splitlines()}
    findings = [
        Finding(".gitignore", 0, f"missing ignore pattern {pattern!r}")
        for pattern in REQUIRED_IGNORES
        if pattern not in present
    ]
    for path in tracked:
        name = Path(path).name
        if name.startswith(".env") and name != ".env.example":
            findings.append(Finding(path, 0, "tracked env file"))
    return findings


def _ip_allowed(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return True  # not an address at all, e.g. a four-part version number
    return text in ALLOWED_IPS or any(ip in net for net in DOC_NETS)


def _email_allowed(match: re.Match[str]) -> bool:
    domain = match.group(1).lower()
    return match.group(0).lower() in ALLOWED_EMAILS or any(
        domain == d or domain.endswith("." + d) for d in ALLOWED_EMAIL_DOMAINS
    )


def check_text(path: str, text: str, identifiers: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    check_patterns = path not in PATTERN_SOURCES
    check_identifiers = path not in IDENTIFIER_EXEMPT
    lowered_ids = [i.lower() for i in identifiers]
    for n, line in enumerate(text.splitlines(), start=1):
        if check_patterns:
            if PERSONAL_PATH.search(line):
                findings.append(Finding(path, n, "personal path"))
            if any(not _email_allowed(m) for m in EMAIL.finditer(line)):
                findings.append(Finding(path, n, "email address"))
            if any(not _ip_allowed(m.group(1)) for m in IPV4.finditer(line)):
                findings.append(Finding(path, n, "ip address"))
            if any(p.search(line) for p in MARKERS):
                findings.append(Finding(path, n, "instruction or attribution marker"))
        if check_identifiers:
            low = line.lower()
            if any(i in low for i in lowered_ids):
                findings.append(Finding(path, n, "personal identifier"))
    return findings


def _env_values(env_file: Path) -> list[str]:
    if not env_file.is_file():
        return []
    values = []
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip("'\"")
        if SENSITIVE_ENV_KEY.search(key.strip()):
            values.append(value)
    return values


def _git_email(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "config", "user.email"], cwd=root, capture_output=True, text=True, check=False
    )
    return [result.stdout.strip()] if result.returncode == 0 else []


def load_identifiers(root: Path) -> list[str]:
    """Values that must never appear in the tree. Loaded at runtime, never printed."""
    ids = _env_values(root / ".env")
    extra = root / ".local" / "privacy-identifiers.txt"
    if extra.is_file():
        ids += [ln.strip() for ln in extra.read_text(encoding="utf-8").splitlines()]
    # Machine-derived values are only meaningful on a developer laptop; CI runners
    # have generic names like "runner" that also appear in ordinary prose.
    if not os.environ.get("CI"):
        ids += _git_email(root)
        ids.append(socket.gethostname().split(".")[0])
        ids.append(Path.home().name)
    seen: set[str] = set()
    unique = []
    for value in ids:
        if len(value) >= MIN_IDENTIFIER_LEN and value.lower() not in seen:
            seen.add(value.lower())
            unique.append(value)
    return unique


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def run(root: Path) -> list[Finding]:
    tracked = tracked_files(root)
    findings = check_gitignore(_read_text(root / ".gitignore") or "", tracked)
    identifiers = load_identifiers(root)
    for rel in tracked:
        text = _read_text(root / rel)
        if text is not None:
            findings += check_text(rel, text, identifiers)
    findings += [Finding(h.path, h.line, f"secret ({h.kind})") for h in scan_secrets(root, tracked)]
    return findings


def main() -> int:
    findings = run(Path.cwd())
    for finding in findings:
        print(finding)
    if findings:
        print(f"privacy check failed: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print("privacy check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
