# Memory and recall v1

## Context

The first memory slice ships `remember`, `forget_memory` and `recall` over MCP before categories,
the gate, redaction, recall events and approvals exist. A few choices fill those gaps until they
land.

## Decision

- **Categories.** Until they exist, a memory has no category and takes the loosest rules: max
  scope org, not confined, injected in work sessions. Cedar still checks scope on every write.
  The `remember` tool has no `category` argument yet, so nothing a client sends is ignored.
- **Where a write lands.** The client names a level, never a key. `user` (the default) is the
  caller's personal scope. `project` and `team` resolve only when the caller belongs to exactly
  one; otherwise the write is refused with `no_scope` or `scope_ambiguous`.
- **Org writes** need a human approval by policy. Approvals don't exist yet, so they're refused
  with `approval_required`, audited, and nothing is stored.
- **Exact duplicates** in the same scope return the existing memory (`created: false`). The
  unique partial index settles concurrent saves; the loser re-runs and finds the winner.
- **Forgotten text** can't be saved again in that tenant (`forgotten_content`).
- **Blocked sessions.** Before searching, recall asks policy whether the session may read a
  memory in the caller's own scope. A revoked or ended session, or an org kill switch, stops
  there, so a blocked session gets a denial rather than an empty result.
- **Recall records** go to the audit log only (memory ids, scope keys, a hash of the query).
  The `recall_events` collection and citation tracking come later.

## Consequences

- Recall has no absolute relevance floor: with few memories, the nearest one comes back even
  for an unrelated query. The relative cutoff only trims weak results when there are strong ones.
- Forget doesn't yet redact evidence turns or entity mentions, because v1 memories have neither.
