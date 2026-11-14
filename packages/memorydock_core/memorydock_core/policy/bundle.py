"""A policy bundle: the Cedar schema, the authz policies and the approval policies, versioned
together. A bundle that fails validation is never served."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cedarpy

FILES = ("schema.cedarschema", "authz.cedar", "approvals.cedar")


class InvalidBundle(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Bundle:
    schema_text: str
    authz_text: str
    approvals_text: str

    @property
    def digest(self) -> str:
        h = hashlib.sha256()
        for text in (self.schema_text, self.authz_text, self.approvals_text):
            # Length-prefix each text so moving bytes between files changes the digest.
            data = text.encode()
            h.update(len(data).to_bytes(8, "big"))
            h.update(data)
        return h.hexdigest()

    @property
    def version(self) -> str:
        return self.digest[:12]

    @property
    def content_hash(self) -> str:
        return f"sha256:{self.digest}"


def load_dir(path: Path) -> Bundle:
    texts = [(path / name).read_text() for name in FILES]
    return Bundle(*texts)


def policy_ids(text: str) -> list[str | None]:
    """The @id of every static policy in `text`, in file order; None where it is missing."""
    doc = json.loads(cedarpy.policies_to_json_str(text))
    policies = doc.get("staticPolicies", {})
    ordered = sorted(policies.items(), key=lambda kv: int(kv[0].removeprefix("policy")))
    return [p.get("annotations", {}).get("id") or None for _, p in ordered]


def validate(bundle: Bundle) -> list[str]:
    """Problems with the bundle; empty means it can be served."""
    problems: list[str] = []
    all_ids: list[str] = []
    for label, text in (("authz", bundle.authz_text), ("approvals", bundle.approvals_text)):
        try:
            ids = policy_ids(text)
        except Exception as exc:  # cedarpy raises plain exceptions on parse errors
            problems.append(f"{label}: does not parse ({type(exc).__name__})")
            continue
        if not ids:
            problems.append(f"{label}: has no policies")
        missing = sum(1 for i in ids if i is None)
        if missing:
            problems.append(f"{label}: {missing} policies without @id")
        all_ids.extend(i for i in ids if i)
        result = cedarpy.validate_policies(text, bundle.schema_text)
        if not result.validation_passed:
            first = str(result.errors[0])[:200] if result.errors else "unknown error"
            problems.append(f"{label}: fails schema validation: {first}")
    dupes = sorted(i for i, n in Counter(all_ids).items() if n > 1)
    if dupes:
        problems.append(f"duplicate @id: {', '.join(dupes)}")
    return problems
