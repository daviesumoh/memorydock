import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

// Browser code reaches the gateway only through the same-origin proxy, which
// adds the access token. Tests pass an absolute base URL.
export function createGatewayClient(baseUrl = "/api/gateway") {
  return createClient<paths>({
    baseUrl,
    // openapi-fetch otherwise keeps the fetch that existed when the client was
    // created, which misses anything that patches fetch later (MSW in tests).
    fetch: (request) => globalThis.fetch(request),
  });
}

export const gateway = createGatewayClient();
