import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { fixtures } from "@/mocks/handlers";
import { server } from "@/mocks/node";

import { createGatewayClient } from "./client";

const client = createGatewayClient("http://localhost:3000/api/gateway");

// Any request without a handler fails the test instead of reaching the network.
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("gateway client", () => {
  it("reads /v1/me through the proxy path", async () => {
    const { data, error, response } = await client.GET("/v1/me");

    expect(error).toBeUndefined();
    expect(new URL(response.url).pathname).toBe("/api/gateway/v1/me");
    expect(data).toEqual(fixtures.me);
  });

  it("surfaces the gateway's error code and request id", async () => {
    server.use(
      http.get("*/api/gateway/v1/me", () =>
        HttpResponse.json(
          { error: { code: "not_signed_in", message: "Sign in to use the console", request_id: "req_1" } },
          { status: 401 },
        ),
      ),
    );
    const { data, error, response } = await client.GET("/v1/me");

    expect(data).toBeUndefined();
    expect(response.status).toBe(401);
    expect(error?.error.code).toBe("not_signed_in");
    expect(error?.error.request_id).toBe("req_1");
  });
});
