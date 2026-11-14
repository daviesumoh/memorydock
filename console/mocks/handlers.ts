import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import { auditEntries, CONSOLE_SESSION, memories, memoryVersions, ROSA, sessions } from "./fixtures";
import { paginate, type PageResult } from "./paging";

// Fictional demo data only. These stand in for gateway routes that are still
// 501 stubs; each handler is removed once its real route lands.
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
} satisfies { me: Schemas["Me"] };

// The leading wildcard matches any origin, so the same handlers serve the
// browser (same-origin proxy) and tests (absolute URLs).
const gatewayPath = (path: `/v1/${string}`) => `*/api/gateway${path}`;

let requestCounter = 0;

function errorResponse(status: number, code: string, message: string) {
  const requestId = `req_mock_${++requestCounter}`;
  return HttpResponse.json(
    { error: { code, message, request_id: requestId, field: null } } satisfies Schemas["ErrorResponse"],
    { status, headers: { "x-request-id": requestId } },
  );
}

function pageResponse<T>(page: PageResult<T>) {
  if ("error" in page) {
    return page.error === "invalid_limit"
      ? errorResponse(422, "invalid_limit", "limit must be between 1 and 100")
      : errorResponse(422, "invalid_cursor", "cursor is not valid for this list");
  }
  return HttpResponse.json(page);
}

// Only the filters the contract defines for each route.
const memoryFilters: Record<string, (memory: Schemas["MemoryOut"], value: string) => boolean> = {
  status: (m, v) => m.status === v,
  type: (m, v) => m.type === v,
};

const auditFilters: Record<string, (entry: Schemas["AuditEntryOut"], value: string) => boolean> = {
  action: (e, v) => e.action === v,
  session_id: (e, v) => e.actor.session_id === v,
  resource_id: (e, v) => e.resource.id === v,
};

function applyFilters<T>(items: T[], filters: Record<string, (item: T, value: string) => boolean>, params: URLSearchParams) {
  return Object.entries(filters).reduce(
    (kept, [name, matches]) => {
      const value = params.get(name);
      return value ? kept.filter((item) => matches(item, value)) : kept;
    },
    items,
  );
}

export const handlers = [
  http.get(gatewayPath("/v1/me"), () => HttpResponse.json(fixtures.me)),

  http.get(gatewayPath("/v1/memories"), ({ request }) => {
    const params = new URL(request.url).searchParams;
    return pageResponse(paginate(applyFilters(memories, memoryFilters, params), (m) => m.id, params));
  }),

  http.get(gatewayPath("/v1/memories/:id"), ({ params }) => {
    const found = memories.find((m) => m.id === params.id);
    return found ? HttpResponse.json(found) : errorResponse(404, "not_found", "No such memory");
  }),

  http.get(gatewayPath("/v1/memories/:id/versions"), ({ request, params }) => {
    const found = memories.find((m) => m.id === params.id);
    if (!found) return errorResponse(404, "not_found", "No such memory");
    const versions: Schemas["MemoryVersionOut"][] = memoryVersions[found.id] ?? [
      {
        id: `memv_${found.id.slice(4)}`,
        memory_id: found.id,
        version: found.version,
        scope_key: found.scope_key,
        status: found.status,
        type: found.type,
        content: found.content,
        change: { kind: "create", by: found.provenance.actor_user, reason: null },
        created_at: found.created_at,
      },
    ];
    return pageResponse(paginate(versions, (v) => v.id, new URL(request.url).searchParams));
  }),

  http.get(gatewayPath("/v1/sessions"), () =>
    HttpResponse.json({ items: sessions, current_session_id: CONSOLE_SESSION } satisfies Schemas["SessionList"]),
  ),

  http.post(gatewayPath("/v1/sessions/:id/:action"), ({ params }) => {
    const found = sessions.find((s) => s.id === params.id);
    if (!found) return errorResponse(404, "not_found", "no such session");
    if (found.id === CONSOLE_SESSION) {
      return errorResponse(409, "current_session", "this is the session the console is using");
    }
    const to = { pause: "paused", resume: "active", revoke: "revoked" }[String(params.action)];
    return to
      ? HttpResponse.json({ ...found, status: to as Schemas["SessionOut"]["status"] })
      : errorResponse(404, "not_found", "no such route");
  }),

  // Registered before /v1/audit so the list handler never answers it.
  http.get(gatewayPath("/v1/audit/verify"), () =>
    HttpResponse.json({ ok: true, checked: auditEntries.length, first_bad_seq: null, reason: "chain verifies" }),
  ),

  http.get(gatewayPath("/v1/audit"), ({ request }) => {
    const params = new URL(request.url).searchParams;
    // Placeholder entries carry no id, so paging keys on seq.
    return pageResponse(paginate(applyFilters(auditEntries, auditFilters, params), (e) => `seq_${e.seq}`, params));
  }),
];
