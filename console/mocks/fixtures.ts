import type { Schemas } from "@/lib/api/client";

// Fictional demo data for the acme org. Never real people or content.

const ROSA = "usr_01JDEMO0ROSA";
const MALIK = "usr_01JDEMO0MALIK";

type Memory = Schemas["Memory"];

function memory(fields: Partial<Memory> & Pick<Memory, "id" | "content" | "type" | "scope_key">): Memory {
  const level = fields.scope_key.split(":", 1)[0] as Memory["scope_level"];
  return {
    scope_level: level,
    status: "active",
    category: null,
    source_client: "claude-code",
    trust: { asserted_by: "extracted_user", confidence: 0.8, flags: 0 },
    version: 1,
    expires_at: null,
    created_at: "2026-11-10T14:02:11.000Z",
    updated_at: "2026-11-10T14:02:11.000Z",
    provenance: {
      source_client: fields.source_client ?? "claude-code",
      captured_by: "distiller",
      actor_user: ROSA,
      session_id: "ses_01JDEMO0A1",
      conversation_id: null,
    },
    valid_from: "2026-11-10T14:02:11.000Z",
    supersedes: null,
    superseded_by: null,
    conflicts_with: [],
    instruction_like: false,
    forgotten: null,
    ...fields,
  };
}

export const memories: Memory[] = [
  memory({
    id: "mem_01JDEMO0001",
    type: "finding",
    scope_key: "project:acme/lantern",
    category: "research",
    source_client: "chatgpt",
    content: "User research on Project Lantern: teams want handoff notes generated at the end of each session.",
    trust: { asserted_by: "user_confirmed", confidence: 0.95, flags: 0 },
    provenance: {
      source_client: "chatgpt",
      captured_by: "extension",
      actor_user: ROSA,
      session_id: "ses_01JDEMO0B2",
      conversation_id: "cnv_demo_lantern_research",
    },
    version: 2,
    created_at: "2026-11-09T16:20:00.000Z",
    updated_at: "2026-11-11T09:12:40.000Z",
  }),
  memory({
    id: "mem_01JDEMO0002",
    type: "decision",
    scope_key: "project:acme/lantern",
    category: "architecture",
    content: "Lantern stores session notes in MongoDB, one document per session.",
    trust: { asserted_by: "user_stated", confidence: 1, flags: 0 },
    created_at: "2026-11-10T11:05:00.000Z",
    updated_at: "2026-11-10T11:05:00.000Z",
  }),
  memory({
    id: "mem_01JDEMO0003",
    type: "preference",
    scope_key: `user:acme/${ROSA}`,
    content: "Prefers small pull requests with one logical change each.",
    source_client: "claude-app",
    created_at: "2026-11-08T08:30:00.000Z",
    updated_at: "2026-11-08T08:30:00.000Z",
  }),
  memory({
    id: "mem_01JDEMO0004",
    type: "procedure",
    scope_key: "team:acme/platform",
    category: "operations",
    content: "Deploys go out from main after CI passes; roll back by redeploying the previous image.",
    source_client: "codex",
    trust: { asserted_by: "agent_inferred", confidence: 0.6, flags: 1 },
  }),
  memory({
    id: "mem_01JDEMO0005",
    type: "fact",
    scope_key: "project:acme/lantern",
    status: "superseded",
    content: "Lantern stores session notes in Postgres.",
    superseded_by: "mem_01JDEMO0002",
    created_at: "2026-11-03T10:00:00.000Z",
    updated_at: "2026-11-10T11:05:00.000Z",
  }),
  memory({
    id: "mem_01JDEMO0006",
    type: "open_question",
    scope_key: "org:acme",
    status: "disputed",
    category: "policy",
    content: "Should session notes be kept for 30 or 90 days?",
    conflicts_with: ["mem_01JDEMO0007"],
    trust: { asserted_by: "extracted_user", confidence: 0.5, flags: 2 },
  }),
  memory({
    id: "mem_01JDEMO0007",
    type: "fact",
    scope_key: "org:acme",
    status: "conflict",
    category: "policy",
    content: "Session notes are kept for 30 days.",
    conflicts_with: ["mem_01JDEMO0006"],
  }),
  memory({
    id: "mem_01JDEMO0008",
    type: "finding",
    scope_key: "project:acme/lantern",
    // Agent-written text is data: it must show as these characters, never run.
    content: 'Saw this in a pasted error page: <script>alert("lantern")</script> <img src=x onerror=alert(1)>',
    source_client: "claude-code",
    instruction_like: true,
    trust: { asserted_by: "agent_inferred", confidence: 0.4, flags: 0 },
  }),
  memory({
    id: "mem_01JDEMO0009",
    type: "fact",
    scope_key: `user:acme/${ROSA}`,
    status: "forgotten",
    content: null,
    forgotten: { by: ROSA, at: "2026-11-12T13:45:00.000Z", reason: "Captured by mistake" },
    created_at: "2026-11-07T12:00:00.000Z",
    updated_at: "2026-11-12T13:45:00.000Z",
  }),
  memory({
    id: "mem_01JDEMO0010",
    type: "episode",
    scope_key: "project:acme/lantern",
    status: "expired",
    content: "Paired on the Lantern export bug; root cause was a stale cursor.",
    expires_at: "2026-11-12T00:00:00.000Z",
    provenance: {
      source_client: "claude-code",
      captured_by: "hook",
      actor_user: MALIK,
      session_id: "ses_01JDEMO0C3",
      conversation_id: null,
    },
  }),
];

export const memoryVersions: Record<string, Schemas["MemoryVersion"][]> = {
  mem_01JDEMO0001: [
    {
      version: 2,
      status: "active",
      type: "finding",
      scope_key: "project:acme/lantern",
      content: "User research on Project Lantern: teams want handoff notes generated at the end of each session.",
      created_at: "2026-11-11T09:12:40.000Z",
    },
    {
      version: 1,
      status: "superseded",
      type: "finding",
      scope_key: "project:acme/lantern",
      content: "User research on Project Lantern: teams want handoff notes.",
      created_at: "2026-11-09T16:20:00.000Z",
    },
  ],
};

function auditEntry(seq: number, fields: Partial<Schemas["AuditEntry"]>): Schemas["AuditEntry"] {
  return {
    id: `aud_01JDEMO${String(seq).padStart(4, "0")}`,
    seq,
    ts: new Date(Date.UTC(2026, 10, 12, 9, 0, seq * 7)).toISOString(),
    actor: { user_id: ROSA, session_id: "ses_01JDEMO0A1", client: "claude-code", via: "mcp" },
    action: "memory.recall",
    resource: { type: "memory", id: null, path: null, scope_keys: ["project:acme/lantern"] },
    decision: { effect: "allow", policy_ids: ["allow-member-read"], policy_version: "3f9c2a1b7d4e" },
    result_status: "ok",
    ...fields,
  };
}

// Newest first, as the route returns them.
export const auditEntries: Schemas["AuditEntry"][] = [
  auditEntry(12, {
    action: "memory.forget",
    actor: { user_id: ROSA, session_id: null, client: "console", via: "console" },
    resource: { type: "memory", id: "mem_01JDEMO0009", path: null, scope_keys: [`user:acme/${ROSA}`] },
    decision: { effect: "allow", policy_ids: ["owner-may-forget"], policy_version: "3f9c2a1b7d4e" },
  }),
  auditEntry(11, {
    action: "lease.acquire",
    actor: { user_id: MALIK, session_id: "ses_01JDEMO0C3", client: "codex", via: "hook" },
    resource: { type: "lease", id: "lse_01JDEMO0001", path: "src/export.ts", scope_keys: ["project:acme/lantern"] },
    decision: { effect: "deny", policy_ids: ["one-holder-per-file"], policy_version: "3f9c2a1b7d4e" },
    result_status: "denied",
  }),
  auditEntry(10, {
    action: "memory.share",
    resource: { type: "memory", id: "mem_01JDEMO0002", path: null, scope_keys: ["org:acme"] },
    decision: { effect: "approval_required", policy_ids: ["org-share-needs-approval"], policy_version: "3f9c2a1b7d4e" },
    result_status: "pending_approval",
  }),
  auditEntry(9, {
    action: "memory.create",
    actor: { user_id: null, session_id: null, client: null, via: "worker" },
    resource: { type: "memory", id: "mem_01JDEMO0001", path: null, scope_keys: ["project:acme/lantern"] },
    decision: { effect: "n/a", policy_ids: [], policy_version: null },
  }),
  auditEntry(8, {
    action: "personal_activity",
    actor: { user_id: null, session_id: null, client: null, via: "mcp" },
    resource: { type: "memory", id: null, path: null, scope_keys: [] },
    decision: { effect: "allow", policy_ids: [], policy_version: null },
    result_status: null,
  }),
  ...Array.from({ length: 7 }, (_, i) =>
    auditEntry(7 - i, {
      resource: { type: "memory", id: null, path: null, scope_keys: ["project:acme/lantern"] },
    }),
  ),
];
