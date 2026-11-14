import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

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

export const handlers = [
  http.get(gatewayPath("/v1/me"), () => HttpResponse.json(fixtures.me)),
];
