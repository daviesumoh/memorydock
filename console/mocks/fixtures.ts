import type { Schemas } from "@/lib/api/client";

// Fictional demo data for the halcyon org. Never real people or content.

export const ROSA = "usr_01JDH0R0SA00000000000000AA";
const MALIK = "usr_01JDH0MA11K0000000000000AA";

type Memory = Schemas["MemoryOut"];

function memory(fields: Partial<Memory> & Pick<Memory, "id" | "content" | "type" | "scope_key">): Memory {
  const level = fields.scope_key.split(":", 1)[0] as Memory["scope_level"];
  return {
    scope_level: level,
    status: "active",
    category: null,
    entities: null,
    provenance: {
      source_client: "claude-code",
      captured_by: "distiller",
      actor_user: ROSA,
      session_id: "ses_01JDEMO0A1",
      conversation_id: null,
    },
    trust: { asserted_by: "extracted_user", confidence: 0.8, flags: 0 },
    valid_from: "2026-11-10T14:02:11.000Z",
    expires_at: null,
    supersedes: null,
    superseded_by: null,
    version: 1,
    forgotten: null,
    created_at: "2026-11-10T14:02:11.000Z",
    updated_at: "2026-11-10T14:02:11.000Z",
    ...fields,
  };
}

type Provenance = Memory["provenance"];

function source(
  client: Provenance["source_client"],
  captured_by: Provenance["captured_by"] = "distiller",
  actor_user = ROSA,
): Provenance {
  return { source_client: client, captured_by, actor_user, session_id: "ses_01JDEMO0A1", conversation_id: null };
}

export const memories: Memory[] = [
  memory({
    id: "mem_01JDEMO0001",
    type: "finding",
    scope_key: "project:halcyon/lantern",
    category: "research",
    entities: ["Lantern"],
    content: "User research on Project Lantern: teams want handoff notes generated at the end of each session.",
    provenance: {
      source_client: "chatgpt",
      captured_by: "extension",
      actor_user: ROSA,
      session_id: "ses_01JDEMO0B2",
      conversation_id: "cnv_demo_lantern_research",
    },
    trust: { asserted_by: "user_confirmed", confidence: 0.95, flags: 0 },
    version: 2,
    created_at: "2026-11-09T16:20:00.000Z",
    updated_at: "2026-11-11T09:12:40.000Z",
  }),
  memory({
    id: "mem_01JDEMO0002",
    type: "decision",
    scope_key: "project:halcyon/lantern",
    category: "architecture",
    content: "Lantern stores session notes in MongoDB, one document per session.",
    supersedes: "mem_01JDEMO0005",
    trust: { asserted_by: "user_stated", confidence: 1, flags: 0 },
    created_at: "2026-11-10T11:05:00.000Z",
    updated_at: "2026-11-10T11:05:00.000Z",
  }),
  memory({
    id: "mem_01JDEMO0003",
    type: "preference",
    scope_key: `user:halcyon/${ROSA}`,
    content: "Prefers small pull requests with one logical change each.",
    provenance: source("claude-app", "mcp_tool"),
    created_at: "2026-11-08T08:30:00.000Z",
    updated_at: "2026-11-08T08:30:00.000Z",
  }),
  memory({
    id: "mem_01JDEMO0004",
    type: "procedure",
    scope_key: "team:halcyon/platform",
    category: "operations",
    content: "Deploys go out from main after CI passes; roll back by redeploying the previous image.",
    provenance: source("codex", "hook"),
    trust: { asserted_by: "agent_inferred", confidence: 0.6, flags: 1 },
  }),
  memory({
    id: "mem_01JDEMO0005",
    type: "fact",
    scope_key: "project:halcyon/lantern",
    status: "superseded",
    content: "Lantern stores session notes in Postgres.",
    superseded_by: "mem_01JDEMO0002",
    created_at: "2026-11-03T10:00:00.000Z",
    updated_at: "2026-11-10T11:05:00.000Z",
  }),
  memory({
    id: "mem_01JDEMO0006",
    type: "open_question",
    scope_key: "org:halcyon",
    status: "disputed",
    category: "policy",
    content: "Should session notes be kept for 30 or 90 days?",
    trust: { asserted_by: "extracted_user", confidence: 0.5, flags: 2 },
  }),
  memory({
    id: "mem_01JDEMO0007",
    type: "fact",
    scope_key: "org:halcyon",
    status: "conflict",
    category: "policy",
    content: "Session notes are kept for 30 days.",
  }),
  memory({
    id: "mem_01JDEMO0008",
    type: "finding",
    scope_key: "project:halcyon/lantern",
    // Agent-written text is data: it must show as these characters, never run.
    content: 'Saw this in a pasted error page: <script>alert("lantern")</script> <img src=x onerror=alert(1)>',
    trust: { asserted_by: "agent_inferred", confidence: 0.4, flags: 0 },
  }),
  memory({
    id: "mem_01JDEMO0009",
    type: "fact",
    scope_key: `user:halcyon/${ROSA}`,
    status: "forgotten",
    content: null,
    forgotten: { by: ROSA, at: "2026-11-12T13:45:00.000Z", reason: "Captured by mistake" },
    created_at: "2026-11-07T12:00:00.000Z",
    updated_at: "2026-11-12T13:45:00.000Z",
  }),
  memory({
    id: "mem_01JDEMO0010",
    type: "episode",
    scope_key: "project:halcyon/lantern",
    status: "expired",
    content: "Paired on the Lantern export bug; root cause was a stale cursor.",
    expires_at: "2026-11-12T00:00:00.000Z",
    provenance: source("claude-code", "hook", MALIK),
  }),
];

export const memoryVersions: Record<string, Schemas["MemoryVersionOut"][]> = {
  mem_01JDEMO0001: [
    {
      id: "memv_01JDEMO0001B",
      memory_id: "mem_01JDEMO0001",
      version: 2,
      scope_key: "project:halcyon/lantern",
      status: "active",
      type: "finding",
      content: "User research on Project Lantern: teams want handoff notes generated at the end of each session.",
      change: { kind: "correct", by: ROSA, reason: "Added when the notes are generated" },
      created_at: "2026-11-11T09:12:40.000Z",
    },
    {
      id: "memv_01JDEMO0001A",
      memory_id: "mem_01JDEMO0001",
      version: 1,
      scope_key: "project:halcyon/lantern",
      status: "superseded",
      type: "finding",
      content: "User research on Project Lantern: teams want handoff notes.",
      change: { kind: "create", by: ROSA, reason: null },
      created_at: "2026-11-09T16:20:00.000Z",
    },
  ],
};

type AuditEntry = Schemas["AuditEntryOut"];

function auditEntry(seq: number, fields: Partial<AuditEntry>): AuditEntry {
  return {
    id: `aud_01JDEMO${String(seq).padStart(4, "0")}`,
    seq,
    ts: new Date(Date.UTC(2026, 10, 12, 9, 0, seq * 7)).toISOString(),
    actor: { user_id: ROSA, session_id: "ses_01JDEMO0A1", client: "claude-code", via: "mcp" },
    action: "memory.recall",
    resource: { type: "memory", id: null, scope_keys: ["project:halcyon/lantern"] },
    decision: { effect: "allow", policy_ids: ["allow-member-read"], policy_version: "3f9c2a1b7d4e" },
    result_status: "ok",
    personal_placeholder: false,
    hash: String(seq % 10).repeat(64),
    prev_hash: String((seq - 1) % 10).repeat(64),
    ...fields,
  };
}

// Newest first, as the route returns them.
export const auditEntries: AuditEntry[] = [
  auditEntry(12, {
    action: "memory.forget",
    actor: { user_id: ROSA, session_id: null, client: "console", via: "console" },
    resource: { type: "memory", id: "mem_01JDEMO0009", scope_keys: [`user:halcyon/${ROSA}`] },
    decision: { effect: "allow", policy_ids: ["owner-may-forget"], policy_version: "3f9c2a1b7d4e" },
  }),
  auditEntry(11, {
    action: "lease.acquire",
    actor: { user_id: MALIK, session_id: "ses_01JDEMO0C3", client: "codex", via: "hook" },
    resource: { type: "lease", id: "lse_01JDEMO0001", scope_keys: ["project:halcyon/lantern"] },
    decision: { effect: "deny", policy_ids: ["one-holder-per-file"], policy_version: "3f9c2a1b7d4e" },
    result_status: "denied",
  }),
  auditEntry(10, {
    action: "memory.share",
    resource: { type: "memory", id: "mem_01JDEMO0002", scope_keys: ["org:halcyon"] },
    decision: { effect: "approval_required", policy_ids: ["org-share-needs-approval"], policy_version: "3f9c2a1b7d4e" },
    result_status: "pending_approval",
  }),
  auditEntry(9, {
    action: "memory.create",
    actor: { user_id: null, session_id: null, client: null, via: "worker" },
    resource: { type: "memory", id: "mem_01JDEMO0001", scope_keys: ["project:halcyon/lantern"] },
    decision: { effect: "n/a", policy_ids: [], policy_version: null },
  }),
  // Another user's personal-scope activity, as an org admin sees it: no ids.
  auditEntry(8, {
    id: null,
    action: "memory.recall",
    actor: { user_id: null, session_id: null, client: null, via: "mcp" },
    resource: { type: "memory", id: null, scope_keys: [] },
    decision: { effect: "allow", policy_ids: [], policy_version: null },
    result_status: null,
    personal_placeholder: true,
  }),
  ...Array.from({ length: 7 }, (_, i) => auditEntry(7 - i, {})),
];

export const CONSOLE_SESSION = "ses_01JDEMO0C0";

export const sessions: Schemas["SessionOut"][] = [
  {
    id: CONSOLE_SESSION,
    user_id: ROSA,
    client: "console",
    status: "active",
    started_at: "2026-11-14T09:00:00Z",
    last_seen_at: "2026-11-14T12:00:00Z",
  },
  {
    id: "ses_01JDEMO0A1",
    user_id: ROSA,
    client: "claude-code",
    status: "active",
    started_at: "2026-11-14T09:05:00Z",
    last_seen_at: "2026-11-14T11:58:00Z",
  },
  {
    id: "ses_01JDEMO0C3",
    user_id: MALIK,
    client: "codex",
    status: "paused",
    started_at: "2026-11-14T08:30:00Z",
    last_seen_at: "2026-11-14T10:15:00Z",
  },
  {
    id: "ses_01JDEMO0D4",
    user_id: MALIK,
    client: "claude-app",
    status: "revoked",
    started_at: "2026-11-13T15:00:00Z",
    last_seen_at: "2026-11-13T16:40:00Z",
  },
];
