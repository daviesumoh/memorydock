"""Scan tracked files for secrets with detect-secrets. Prints file:line: type, never the value."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings

# Lockfiles are full of integrity hashes that read as high-entropy strings.
SKIP_FILES = {"uv.lock", "pnpm-lock.yaml"}


@dataclass(frozen=True)
class SecretHit:
    path: str
    line: int
    kind: str


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "-z"], cwd=root, check=True, capture_output=True
    ).stdout.decode()
    return [p for p in out.split("\0") if p]


def scan(root: Path, files: list[str]) -> list[SecretHit]:
    collection = SecretsCollection(root=str(root))
    with default_settings():
        for rel in files:
            if Path(rel).name in SKIP_FILES or not (root / rel).is_file():
                continue
            collection.scan_file(rel)
    hits = [
        SecretHit(path=filename, line=secret.line_number or 0, kind=secret.type)
        for filename, secret in collection
    ]
    return sorted(hits, key=lambda h: (h.path, h.line, h.kind))


def main() -> int:
    root = Path.cwd()
    hits = scan(root, tracked_files(root))
    for hit in hits:
        print(f"{hit.path}:{hit.line}: secret ({hit.kind})")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
