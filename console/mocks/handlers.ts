import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import { auditEntries, memories, memoryVersions } from "./fixtures";
import { paginate, type PageResult } from "./paging";

// Fictional demo data only. These stand in for gateway routes that are still
// 501 stubs; each handler is removed once its real route lands.
export const fixtures = {
  me: {
    user_id: "usr_01JDEMO0ROSA",
    email: "rosa@example.com",
    org_id: "org_acme",
  },
} satisfies { me: Schemas["Me"] };

// The leading wildcard matches any origin, so the same handlers serve the
// browser (same-origin proxy) and tests (absolute URLs).
const gatewayPath = (path: `/v1/${string}`) => `*/api/gateway${path}`;

let requestCounter = 0;

function errorResponse(status: number, code: string, message: string) {
  const requestId = `req_mock_${++requestCounter}`;
  return HttpResponse.json(
    { error: { code, message, request_id: requestId } } satisfies Schemas["ErrorResponse"],
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

const memoryFilters: Record<string, (memory: Schemas["Memory"], value: string) => boolean> = {
  scope: (m, v) => m.scope_key === v,
  type: (m, v) => m.type === v,
  status: (m, v) => m.status === v,
  category: (m, v) => m.category === v,
  source_client: (m, v) => m.source_client === v,
  project: (m, v) => m.scope_key === `project:acme/${v}`,
};

const auditFilters: Record<string, (entry: Schemas["AuditEntry"], value: string) => boolean> = {
  session_id: (e, v) => e.actor.session_id === v,
  user_id: (e, v) => e.actor.user_id === v,
  resource_id: (e, v) => e.resource.id === v,
  action: (e, v) => e.action === v,
  // Fixtures carry no task ids, so a task filter matches nothing.
  task_id: () => false,
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

function toSummary(memory: Schemas["Memory"]): Schemas["MemorySummary"] {
  const { id, scope_key, scope_level, type, status, category, content, source_client, trust, version, expires_at, created_at, updated_at } = memory;
  return { id, scope_key, scope_level, type, status, category, content, source_client, trust, version, expires_at, created_at, updated_at };
}

export const handlers = [
  http.get(gatewayPath("/v1/me"), () => HttpResponse.json(fixtures.me)),

  http.get(gatewayPath("/v1/memories"), ({ request }) => {
    const params = new URL(request.url).searchParams;
    const matching = applyFilters(memories, memoryFilters, params).map(toSummary);
    return pageResponse(paginate(matching, (m) => m.id, params));
  }),

  http.get(gatewayPath("/v1/memories/:id"), ({ params }) => {
    const found = memories.find((m) => m.id === params.id);
    return found ? HttpResponse.json(found) : errorResponse(404, "not_found", "No such memory");
  }),

  http.get(gatewayPath("/v1/memories/:id/versions"), ({ request, params }) => {
    const found = memories.find((m) => m.id === params.id);
    if (!found) return errorResponse(404, "not_found", "No such memory");
    const versions = memoryVersions[found.id] ?? [
      { version: found.version, status: found.status, type: found.type, scope_key: found.scope_key, content: found.content, created_at: found.updated_at },
    ];
    return pageResponse(paginate(versions, (v) => String(v.version), new URL(request.url).searchParams));
  }),

  http.get(gatewayPath("/v1/audit"), ({ request }) => {
    const params = new URL(request.url).searchParams;
    return pageResponse(paginate(applyFilters(auditEntries, auditFilters, params), (e) => e.id, params));
  }),
];
