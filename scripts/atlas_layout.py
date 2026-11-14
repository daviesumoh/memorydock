"""The desired Atlas layout (validators, indexes, search indexes) as read from infra/atlas/."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ATLAS_DIR = Path(__file__).resolve().parent.parent / "infra" / "atlas"

# Collections without a tenant: global policy bookkeeping, per-tenant heads keyed by tenant id,
# and orgs, whose _id is the tenant id.
UNTENANTED = {"orgs", "policies", "policy_heads", "audit_heads"}


@dataclass(frozen=True)
class IndexSpec:
    name: str
    keys: tuple[tuple[str, int], ...]
    unique: bool = False
    partial: dict[str, Any] | None = None
    ttl_seconds: int | None = None


@dataclass(frozen=True)
class SearchIndexSpec:
    collection: str
    name: str
    type: str
    definition: dict[str, Any]


@dataclass(frozen=True)
class Layout:
    validators: dict[str, dict[str, Any]]
    indexes: dict[str, list[IndexSpec]]
    search_indexes: list[SearchIndexSpec]

    @property
    def collections(self) -> list[str]:
        return sorted(self.validators)


def _substitute(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        for name, replacement in variables.items():
            value = value.replace("${" + name + "}", replacement)
        return value
    if isinstance(value, list):
        return [_substitute(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, variables) for k, v in value.items()}
    return value


def load_layout(variables: dict[str, str], atlas_dir: Path = ATLAS_DIR) -> Layout:
    validators = {
        path.stem: json.loads(path.read_text())
        for path in sorted((atlas_dir / "validators").glob("*.json"))
    }
    raw_indexes = json.loads((atlas_dir / "indexes.json").read_text())
    indexes = {
        coll: [
            IndexSpec(
                name=spec["name"],
                keys=tuple((field, int(direction)) for field, direction in spec["keys"]),
                unique=bool(spec.get("unique", False)),
                partial=spec.get("partial"),
                ttl_seconds=spec.get("ttl_seconds"),
            )
            for spec in specs
        ]
        for coll, specs in raw_indexes.items()
    }
    search = []
    for path in sorted((atlas_dir / "search_indexes").glob("*.json")):
        collection, name = path.stem.split(".", 1)
        doc = _substitute(json.loads(path.read_text()), variables)
        search.append(SearchIndexSpec(collection, name, doc["type"], doc["definition"]))
    return Layout(validators, indexes, search)
