import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

// Fictional demo data only. These stand in for gateway routes that are still
// 501 stubs; each handler is removed once its real route lands.
const ROSA = "usr_01JDH0R0SA00000000000000AA";
const MEMORY = "mem_01JDH0MEM0000000000000000A";
const NOW = "2026-11-14T12:00:00Z";

const memory: Schemas["MemoryOut"] = {
  id: MEMORY,
  scope_key: "project:halcyon/lantern",
  scope_level: "project",
  type: "decision",
  status: "active",
  category: "product",
  content: "Onboarding must take under 3 minutes; drop the team invite step.",
  entities: ["Lantern"],
  provenance: {
    source_client: "chatgpt",
    captured_by: "extension",
    actor_user: ROSA,
    session_id: null,
    conversation_id: null,
  },
  trust: { asserted_by: "extracted_user", confidence: 0.85, flags: 0 },
  valid_from: NOW,
  expires_at: null,
  supersedes: null,
  superseded_by: null,
  version: 1,
  forgotten: null,
  created_at: NOW,
  updated_at: NOW,
};

export const fixtures = {
  me: {
    user_id: ROSA,
    email: "rosa@example.com",
    org_id: "halcyon",
    display_name: "Rosa",
    roles: ["member"],
    teams: ["product"],
    projects: [{ slug: "lantern", name: "Project Lantern", maintainer: true }],
  },
  memory,
  memories: { items: [memory], next_cursor: null },
  versions: {
    items: [
      {
        id: "memv_01JDH0MEMV000000000000000A",
        memory_id: MEMORY,
        version: 1,
        scope_key: memory.scope_key,
        status: "active",
        type: "decision",
        content: memory.content,
        change: { kind: "create", by: ROSA, reason: null },
        created_at: NOW,
      },
    ],
    next_cursor: null,
  },
  audit: {
    items: [
      {
        id: "aud_01JDH0AUD0000000000000000A",
        seq: 1,
        ts: NOW,
        actor: { user_id: ROSA, session_id: null, client: "chatgpt", via: "rest" },
        action: "memory.create",
        resource: { type: "memory", id: MEMORY, scope_keys: [memory.scope_key] },
        decision: { effect: "allow", policy_ids: ["memory-write-member"], policy_version: "a1b2c3d4e5f6" },
        result_status: "ok",
        personal_placeholder: false,
        hash: "b".repeat(64),
        prev_hash: "0".repeat(64),
      },
    ],
    next_cursor: null,
  },
} satisfies {
  me: Schemas["Me"];
  memory: Schemas["MemoryOut"];
  memories: Schemas["MemoryPage"];
  versions: Schemas["MemoryVersionPage"];
  audit: Schemas["AuditPage"];
};

// The leading wildcard matches any origin, so the same handlers serve the
// browser (same-origin proxy) and tests (absolute URLs).
const gatewayPath = (path: `/v1/${string}`) => `*/api/gateway${path}`;

export const handlers = [
  http.get(gatewayPath("/v1/me"), () => HttpResponse.json(fixtures.me)),
  http.get(gatewayPath("/v1/memories"), () => HttpResponse.json(fixtures.memories)),
  http.get(gatewayPath("/v1/memories/:id"), () => HttpResponse.json(fixtures.memory)),
  http.get(gatewayPath("/v1/memories/:id/versions"), () => HttpResponse.json(fixtures.versions)),
  http.get(gatewayPath("/v1/audit"), () => HttpResponse.json(fixtures.audit)),
];
