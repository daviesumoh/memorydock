"""Only the repository layer (core/repo/) and core/db.py talk to Atlas. Everything else calls
repo functions, which add the tenant and scope filters themselves."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "packages" / "memorydock_core" / "memorydock_core"
SCANNED = [CORE, ROOT / "services"]
ALLOWED = [CORE / "repo", CORE / "db.py"]

FORBIDDEN = {
    "collection access": re.compile(r"\bdb\.[a-z_]\w*"),
    "collection indexing": re.compile(r"\bdb\["),
    "get_collection": re.compile(r"\.get_collection\("),
    "client construction": re.compile(r"\b(?:Async)?MongoClient\("),
}


def offenders() -> list[str]:
    found = []
    for base in SCANNED:
        for path in sorted(base.rglob("*.py")):
            if any(path == a or a in path.parents for a in ALLOWED):
                continue
            for n, line in enumerate(path.read_text().splitlines(), start=1):
                code = line.split("#", 1)[0]
                for kind, pattern in FORBIDDEN.items():
                    if pattern.search(code):
                        found.append(f"{path.relative_to(ROOT)}:{n}: {kind}")
    return found


def test_database_access_stays_in_the_repository_layer():
    assert offenders() == []


def test_the_check_catches_violations(tmp_path, monkeypatch):
    bad = tmp_path / "services" / "x.py"
    bad.parent.mkdir()
    bad.write_text('await db.memories.find_one({})\nc = AsyncMongoClient("u")\nx = db["turns"]\n')
    monkeypatch.setattr(__import__(__name__), "SCANNED", [tmp_path / "services"])
    monkeypatch.setattr(__import__(__name__), "ROOT", tmp_path)
    assert len(offenders()) == 3
