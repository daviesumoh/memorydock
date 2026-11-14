"""What a domain operation needs to act for a caller: the database, the policy in force, who is
calling, through which surface, and when. Built once per request by the transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, NoReturn

from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from memorydock_core.audit import events
from memorydock_core.audit.events import AuditEvent, Resource, Via
from memorydock_core.errors import Forbidden
from memorydock_core.policy import entities
from memorydock_core.policy.pdp import PDP, Decision, Request, uid
from memorydock_core.principal import Principal
from memorydock_core.repo import audit as audit_repo
from memorydock_core.txn import run_transaction


@dataclass(frozen=True)
class Op:
    client: AsyncMongoClient[dict[str, Any]]
    db: AsyncDatabase[dict[str, Any]]
    pdp: PDP
    principal: Principal
    via: Via
    now: datetime

    def authorize_memories(
        self, action: str, docs: list[dict[str, Any]], context: dict[str, Any] | None = None
    ) -> list[Decision]:
        if not docs:
            return []
        world = entities.for_principal(self.principal) + [entities.memory_doc(d) for d in docs]
        session = uid("AgentSession", self.principal.session_id)
        requests = [
            Request(session, action, uid("Memory", str(d["_id"])), context or {}) for d in docs
        ]
        return self.pdp.authorize_batch(requests, world)

    async def append_audit(self, session: AsyncClientSession, event: AuditEvent) -> None:
        await audit_repo.append(self.db, session, self.principal, event, now=self.now)

    async def audit_only(self, event: AuditEvent) -> None:
        async def write(session: AsyncClientSession) -> None:
            await self.append_audit(session, event)

        await run_transaction(self.client, write)

    async def refuse(self, action: str, resource: Resource, decision: Decision) -> NoReturn:
        """Audit a denied or approval-gated request, then raise. Raises always."""
        await self.audit_only(
            events.by_principal(
                self.principal,
                self.via,
                action,
                resource,
                decision=events.from_decision(decision),
                result="denied" if decision.effect == "deny" else "approval_required",
            )
        )
        if decision.effect == "approval_required":
            raise Forbidden(
                "this needs a human approval, which isn't available yet",
                code="approval_required",
            )
        raise Forbidden("policy does not allow this", code="policy_denied")
