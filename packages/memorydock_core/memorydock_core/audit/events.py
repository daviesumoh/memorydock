"""What callers hand to the audit writer. Never memory content, turn text or tokens."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from memorydock_core.policy.pdp import Decision
    from memorydock_core.principal import Principal

Via = Literal["mcp", "rest", "hook", "worker", "console", "webhook", "system"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Actor(_Strict):
    via: Via
    user_id: str | None = None
    session_id: str | None = None
    client: str | None = None
    model: str | None = None
    machine_id: str | None = None


class Resource(_Strict):
    type: str
    id: str | None = None
    path: str | None = None
    scope_keys: list[str] = Field(default_factory=list)


class DecisionRecord(_Strict):
    effect: Literal["allow", "deny", "approval_required", "n/a"]
    policy_ids: list[str] = Field(default_factory=list)
    policy_version: str | None = Field(default=None, pattern=r"^[a-f0-9]{12}$")
    approval_id: str | None = None


class Why(_Strict):
    intent: str | None = None
    task_id: str | None = None
    step_id: str | None = None
    prompt_hash: str | None = None
    memory_ids_in_context: list[str] = Field(default_factory=list)


class Result(_Strict):
    status: str
    effect_id: str | None = None
    external_ref: dict[str, str] | None = None
    verification: str | None = None


class AuditEvent(_Strict):
    actor: Actor
    action: str = Field(pattern=r"^[a-z_]+(\.[a-z_]+)+$", max_length=100)
    resource: Resource
    decision: DecisionRecord
    why: Why = Field(default_factory=Why)
    result: Result
    input_hash: str | None = None
    diff_hash: str | None = None


def from_decision(decision: Decision) -> DecisionRecord:
    """A policy Decision as the audit log records it."""
    return DecisionRecord(
        effect=decision.effect,
        policy_ids=list(decision.policy_ids),
        policy_version=decision.policy_version,
    )


def by_principal(
    p: Principal,
    via: Via,
    action: str,
    resource: Resource,
    *,
    decision: DecisionRecord,
    result: str,
    why: Why | None = None,
    diff_hash: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        actor=Actor(via=via, user_id=p.user_id, session_id=p.session_id, client=p.client),
        action=action,
        resource=resource,
        decision=decision,
        why=why or Why(),
        result=Result(status=result),
        diff_hash=diff_hash,
    )
