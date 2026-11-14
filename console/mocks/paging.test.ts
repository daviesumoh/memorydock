import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { testGateway as client } from "@/test/gateway-client";

import { memories } from "./fixtures";
import { server } from "./node";
import { encodeCursor } from "./paging";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// The mocks must page the way the gateway will, or the console is tested
// against behaviour it will never see.
describe("mock memory paging", () => {
  it("walks every memory exactly once across pages", async () => {
    const seen: string[] = [];
    let cursor: string | undefined;
    let pages = 0;
    do {
      const { data } = await client.GET("/v1/memories", { params: { query: { limit: 3, cursor } } });
      seen.push(...data!.items.map((m) => m.id));
      cursor = data!.next_cursor ?? undefined;
      pages += 1;
    } while (cursor && pages < 20);

    expect(pages).toBe(Math.ceil(memories.length / 3));
    expect(new Set(seen).size).toBe(seen.length);
    expect(seen).toEqual(memories.map((m) => m.id));
  });

  const asCursor = (value: unknown) => btoa(JSON.stringify(value)).replace(/=+$/, "");

  it.each([
    ["characters outside base64url", "not-base64!"],
    ["an id that is not on the list", encodeCursor("mem_nope")],
    ["an unknown cursor version", asCursor({ k: "mem_01JDEMO0001", v: 2 })],
    ["a key that is not a string", asCursor({ k: 7, v: 1 })],
    ["an empty cursor", ""],
  ])("answers 422 invalid_cursor for %s", async (_label, cursor) => {
    const { error, response } = await client.GET("/v1/memories", { params: { query: { cursor } } });
    expect(response.status).toBe(422);
    expect(error?.error.code).toBe("invalid_cursor");
  });

  it.each([0, 101, 2.5])("answers 422 invalid_limit for limit %s", async (limit) => {
    const { error, response } = await client.GET("/v1/memories", { params: { query: { limit } } });
    expect(response.status).toBe(422);
    expect(error?.error.code).toBe("invalid_limit");
  });

  it("filters before paging, so a filtered list has no gaps", async () => {
    const { data } = await client.GET("/v1/memories", { params: { query: { status: "active", limit: 100 } } });
    expect(data!.items.length).toBeGreaterThan(0);
    expect(data!.items.every((m) => m.status === "active")).toBe(true);
  });
});
