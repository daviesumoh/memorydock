import { afterEach, describe, expect, it, vi } from "vitest";

import { buildUpstreamUrl, forwardToGateway, isForwardablePath } from "./gateway-proxy";

const TOKEN = "eyJhbGciOiJSUzI1NiJ9.test-access-token.signature";
const GATEWAY = new URL("https://gateway.example.com");

function stubFetch(impl: (url: URL, init: RequestInit) => Promise<Response>) {
  const fetchMock = vi.fn(impl);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastCall(fetchMock: ReturnType<typeof stubFetch>) {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url, init, headers: new Headers(init.headers) };
}

function logSpies() {
  return (["log", "info", "warn", "error", "debug"] as const).map((level) =>
    vi.spyOn(console, level).mockImplementation(() => {}),
  );
}

function expectTokenNeverLogged(spies: ReturnType<typeof logSpies>) {
  for (const spy of spies) {
    for (const args of spy.mock.calls) {
      expect(JSON.stringify(args)).not.toContain(TOKEN);
    }
  }
}

describe("isForwardablePath", () => {
  it.each([
    [["v1", "me"]],
    [["v1", "memories", "mem_01"]],
    [["v1", "stream", "audit"]],
  ])("accepts %j", (path) => {
    expect(isForwardablePath(path)).toBe(true);
  });

  it.each([
    [[]],
    [["v1"]],
    [["healthz"]],
    [["mcp"]],
    [["v2", "me"]],
    [["v1", "..", "mcp"]],
    [["v1", ".", "me"]],
    [["v1", "", "me"]],
  ])("refuses %j", (path) => {
    expect(isForwardablePath(path)).toBe(false);
  });
});

describe("buildUpstreamUrl", () => {
  it("keeps the query string and a base path on the gateway URL", () => {
    const url = buildUpstreamUrl(new URL("https://gw.example.com/base/"), ["v1", "audit"], "?cursor=abc");
    expect(url.toString()).toBe("https://gw.example.com/base/v1/audit?cursor=abc");
  });

  it("encodes a segment that carries a slash so it stays one segment", () => {
    const url = buildUpstreamUrl(GATEWAY, ["v1", "memories", "a/../../mcp"], "");
    expect(url.pathname).toBe("/v1/memories/a%2F..%2F..%2Fmcp");
  });
});

describe("forwardToGateway", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns 401 without calling the gateway when there is no session", async () => {
    const fetchMock = stubFetch(async () => new Response("{}"));
    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: null,
      gatewayUrl: GATEWAY,
    });

    expect(response.status).toBe(401);
    expect(await response.json()).toMatchObject({ code: "not_signed_in" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 404 without calling the gateway for a path outside /v1", async () => {
    const fetchMock = stubFetch(async () => new Response("{}"));
    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/mcp"),
      path: ["mcp"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({ code: "not_found" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the session token as a bearer token to the matching gateway route", async () => {
    const fetchMock = stubFetch(async () => Response.json({ user_id: "usr_1" }));
    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/memories?limit=20"),
      path: ["v1", "memories"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    const { url, headers } = lastCall(fetchMock);
    expect(url.toString()).toBe("https://gateway.example.com/v1/memories?limit=20");
    expect(headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ user_id: "usr_1" });
  });

  it("replaces a client-supplied Authorization header and drops cookies", async () => {
    const fetchMock = stubFetch(async () => new Response(null, { status: 204 }));
    await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me", {
        headers: {
          authorization: "Bearer forged",
          cookie: "wos-session=sealed-session-cookie",
          "x-forwarded-for": "198.51.100.7",
          accept: "application/json",
        },
      }),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    const { headers } = lastCall(fetchMock);
    expect(headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(headers.get("cookie")).toBeNull();
    expect(headers.get("x-forwarded-for")).toBeNull();
    expect(headers.get("accept")).toBe("application/json");
  });

  it("forwards If-Match and Last-Event-ID, which edits and stream resumes depend on", async () => {
    const fetchMock = stubFetch(async () => new Response(null, { status: 204 }));
    await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/memories/mem_1", {
        method: "PATCH",
        headers: { "if-match": '"3"', "last-event-id": "evt_9", "content-type": "application/json" },
        body: JSON.stringify({ content: "edited" }),
      }),
      path: ["v1", "memories", "mem_1"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    const { init, headers } = lastCall(fetchMock);
    expect(init.method).toBe("PATCH");
    expect(headers.get("if-match")).toBe('"3"');
    expect(headers.get("last-event-id")).toBe("evt_9");
    expect(await new Response(init.body).text()).toBe(JSON.stringify({ content: "edited" }));
  });

  it("does not send a body on GET", async () => {
    const fetchMock = stubFetch(async () => new Response("{}"));
    await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    expect(lastCall(fetchMock).init.body).toBeUndefined();
  });

  it("passes gateway errors through with their status and body", async () => {
    stubFetch(async () =>
      Response.json(
        { code: "session_revoked", message: "Session revoked", request_id: "req_gw" },
        { status: 403, headers: { "x-request-id": "req_gw" } },
      ),
    );
    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    expect(response.status).toBe(403);
    expect(response.headers.get("x-request-id")).toBe("req_gw");
    expect(await response.json()).toMatchObject({ code: "session_revoked" });
  });

  it("never passes Set-Cookie from the gateway to the browser", async () => {
    stubFetch(
      async () =>
        new Response("{}", { headers: { "set-cookie": "planted=1", "content-type": "application/json" } }),
    );
    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    expect(response.headers.get("set-cookie")).toBeNull();
    expect(response.headers.get("content-type")).toBe("application/json");
  });

  it.each([
    ["text/html; charset=utf-8", "<script>alert(document.cookie)</script>"],
    ["image/svg+xml", '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'],
    ["text/plain", "<script>alert(1)</script>"],
  ])("refuses a %s response so its body never renders on the console origin", async (contentType, body) => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    stubFetch(async () => new Response(body, { status: 200, headers: { "content-type": contentType } }));
    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/memories/mem_1"),
      path: ["v1", "memories", "mem_1"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    expect(response.status).toBe(502);
    expect(response.headers.get("content-type")).toBe("application/json");
    const text = await response.text();
    expect(text).not.toContain("<script");
    expect(text).not.toContain("onload");
    expect(JSON.parse(text)).toMatchObject({ code: "gateway_bad_response" });
  });

  it("refuses a body that has no content type, since a browser would sniff it", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const untyped = new Response(new Blob(["<html><script>alert(1)</script></html>"]).stream());
    expect(untyped.headers.get("content-type")).toBeNull();
    stubFetch(async () => untyped);
    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    expect(response.status).toBe(502);
  });

  it("accepts JSON with a charset parameter and bodiless responses", async () => {
    stubFetch(async () => new Response('{"ok":true}', { headers: { "content-type": "Application/JSON; charset=utf-8" } }));
    const json = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });
    expect(json.status).toBe(200);

    stubFetch(async () => new Response(null, { status: 204 }));
    const empty = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/memories/mem_1", { method: "DELETE" }),
      path: ["v1", "memories", "mem_1"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });
    expect(empty.status).toBe(204);
  });

  it("sends nosniff and a sandboxing CSP on forwarded responses and on the proxy's own errors", async () => {
    stubFetch(async () => Response.json({ ok: true }));
    const forwarded = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });
    const ownError = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: null,
      gatewayUrl: GATEWAY,
    });

    for (const response of [forwarded, ownError]) {
      expect(response.headers.get("x-content-type-options")).toBe("nosniff");
      expect(response.headers.get("content-security-policy")).toContain("sandbox");
      expect(response.headers.get("content-security-policy")).toContain("default-src 'none'");
    }
  });

  it("streams an event stream through as chunks arrive instead of buffering it", async () => {
    let pushSecond!: () => void;
    const encoder = new TextEncoder();
    const upstreamBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("id: 1\ndata: first\n\n"));
        pushSecond = () => {
          controller.enqueue(encoder.encode("id: 2\ndata: second\n\n"));
          controller.close();
        };
      },
    });
    stubFetch(async () => new Response(upstreamBody, { headers: { "content-type": "text/event-stream" } }));

    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/stream/audit"),
      path: ["v1", "stream", "audit"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    expect(response.headers.get("content-type")).toBe("text/event-stream");
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    // The first event is readable while the gateway is still holding the stream open.
    expect(decoder.decode((await reader.read()).value)).toBe("id: 1\ndata: first\n\n");
    pushSecond();
    expect(decoder.decode((await reader.read()).value)).toBe("id: 2\ndata: second\n\n");
    expect((await reader.read()).done).toBe(true);
  });

  it("returns 502 and logs no token when the gateway is unreachable", async () => {
    const spies = logSpies();
    stubFetch(async () => {
      throw new TypeError("fetch failed");
    });
    const response = await forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });

    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body).toMatchObject({ code: "gateway_unreachable" });
    expect(body.request_id).toBe(response.headers.get("x-request-id"));
    expect(JSON.stringify(body)).not.toContain(TOKEN);
    expectTokenNeverLogged(spies);
  });

  it("returns 504 and logs no token when the gateway sends no headers in time", async () => {
    vi.useFakeTimers();
    const spies = logSpies();
    stubFetch(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const pending = forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/me"),
      path: ["v1", "me"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
      headersTimeoutMs: 1_000,
    });
    await vi.advanceTimersByTimeAsync(1_000);
    const response = await pending;

    expect(response.status).toBe(504);
    expect(await response.json()).toMatchObject({ code: "gateway_timeout" });
    expectTokenNeverLogged(spies);
  });

  it("cancels the gateway call when the browser disconnects, without logging a failure", async () => {
    const spies = logSpies();
    const browser = new AbortController();
    const fetchMock = stubFetch(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const pending = forwardToGateway({
      request: new Request("http://localhost:3000/api/gateway/v1/stream/audit", { signal: browser.signal }),
      path: ["v1", "stream", "audit"],
      accessToken: TOKEN,
      gatewayUrl: GATEWAY,
    });
    browser.abort();
    await pending;

    expect(lastCall(fetchMock).init.signal!.aborted).toBe(true);
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});
