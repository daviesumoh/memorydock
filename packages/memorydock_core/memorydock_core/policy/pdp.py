"""The policy decision point. Every surface calls authorize() before acting.

authz.cedar decides allow or deny. Only when it allows are the approval policies evaluated;
a permit there turns the result into approval_required.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

import cedarpy

from memorydock_core.policy.bundle import Bundle, InvalidBundle, validate

log = logging.getLogger("memorydock.policy")

NS = "Memorydock"
Effect = Literal["allow", "deny", "approval_required"]


@dataclass(frozen=True)
class Decision:
    effect: Effect
    policy_ids: tuple[str, ...]
    policy_version: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"


@dataclass(frozen=True)
class Request:
    principal: str  # entity uid, e.g. Memorydock::AgentSession::"ses_..."
    action: str  # e.g. "memory.read"
    resource: str
    context: dict[str, Any]


def uid(kind: str, eid: str) -> str:
    # Ids are prefixed ULIDs or slugs; quotes and backslashes never appear in them.
    if '"' in eid or "\\" in eid:
        raise ValueError("entity id contains a quote or backslash")
    return f'{NS}::{kind}::"{eid}"'


class PDP:
    def __init__(self, bundle: Bundle) -> None:
        problems = validate(bundle)
        if problems:
            raise InvalidBundle(problems)
        self.version = bundle.version
        self._schema = bundle.schema_text
        self._authz = cedarpy.PolicySet.from_str(bundle.authz_text)
        self._approvals = cedarpy.PolicySet.from_str(bundle.approvals_text)

    def authorize(self, request: Request, entities: list[dict[str, Any]]) -> Decision:
        return self.authorize_batch([request], entities)[0]

    def authorize_batch(
        self, requests: list[Request], entities: list[dict[str, Any]]
    ) -> list[Decision]:
        cedar_requests = [self._cedar_request(r) for r in requests]
        authz = cedarpy.is_authorized_batch(cedar_requests, self._authz, entities, self._schema)
        decisions: list[Decision | None] = [None] * len(requests)
        needs_approval_check = []
        for i, result in enumerate(authz):
            ids = self._ids(result)
            if result.diagnostics.errors:
                # Cedar skips a policy that errors, so a broken forbid would quietly allow.
                log.warning("policy evaluation errors: %d", len(result.diagnostics.errors))
                decisions[i] = Decision("deny", ids, self.version, "policy evaluation error")
            elif not result.allowed:
                reason = f"forbidden by {', '.join(ids)}" if ids else "no policy permits this"
                decisions[i] = Decision("deny", ids, self.version, reason)
            else:
                needs_approval_check.append(i)
        if needs_approval_check:
            approvals = cedarpy.is_authorized_batch(
                [cedar_requests[i] for i in needs_approval_check],
                self._approvals,
                entities,
                self._schema,
            )
            for i, result in zip(needs_approval_check, approvals, strict=True):
                allow_ids = self._ids(authz[i])
                if result.allowed and not result.diagnostics.errors:
                    ids = allow_ids + self._ids(result)
                    decisions[i] = Decision(
                        "approval_required", ids, self.version, "needs human approval"
                    )
                else:
                    decisions[i] = Decision("allow", allow_ids, self.version, "permitted")
        return [d for d in decisions if d is not None]

    @staticmethod
    def _cedar_request(r: Request) -> dict[str, Any]:
        return {
            "principal": r.principal,
            "action": f'{NS}::Action::"{r.action}"',
            "resource": r.resource,
            "context": r.context,
        }

    @staticmethod
    def _ids(result: Any) -> tuple[str, ...]:
        by_reason = result.diagnostics.id_annotations_by_reason or {}
        return tuple(sorted(by_reason.get(r, r) for r in result.diagnostics.reasons))
