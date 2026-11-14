import { describe, expect, it } from "vitest";

import { actionFor, backoffMs, countResults, MAX_BODY_BYTES, MAX_TURN_CHARS, takeBatch } from "./batching.ts";
import type { Turn } from "./turns.ts";

const turn = (n: number, text = "hello"): Turn => ({
  client_turn_id: `t${n}`,
  conversation_id: "cnv_1",
  seq: n,
  role: "user",
  text,
  ts: "2026-11-14T12:00:00.000Z",
  meta: {},
});

const bodyBytes = (batch: Turn[]) => new TextEncoder().encode(JSON.stringify(batch)).length;

describe("takeBatch", () => {
  it("takes at most 20 turns, in order, and leaves the rest queued", () => {
    const queue = Array.from({ length: 45 }, (_, i) => turn(i + 1));
    const { batch, rest } = takeBatch(queue);
    expect(batch.map((t) => t.seq)).toEqual(Array.from({ length: 20 }, (_, i) => i + 1));
    expect(rest).toHaveLength(25);
    expect(rest[0].seq).toBe(21);
  });

  it("returns an empty batch for an empty queue", () => {
    expect(takeBatch([])).toEqual({ batch: [], rest: [] });
  });

  it("stops before the body would pass the size limit", () => {
    const queue = Array.from({ length: 12 }, (_, i) => turn(i + 1, "x".repeat(MAX_TURN_CHARS)));
    const { batch, rest } = takeBatch(queue);
    expect(batch.length).toBeGreaterThan(0);
    expect(batch.length).toBeLessThan(12);
    expect(bodyBytes(batch)).toBeLessThanOrEqual(MAX_BODY_BYTES + batch.length + 2);
    expect(batch.length + rest.length).toBe(12);
  });

  it("cuts an oversized turn to the limit instead of blocking the queue behind it", () => {
    const { batch, rest } = takeBatch([turn(1, "y".repeat(MAX_TURN_CHARS + 500)), turn(2)]);
    expect(batch[0].text).toHaveLength(MAX_TURN_CHARS);
    expect(batch[1].seq).toBe(2);
    expect(rest).toEqual([]);
  });

  it("does not cut through the middle of an emoji", () => {
    const text = "a".repeat(MAX_TURN_CHARS - 1) + "\u{1F600}";
    const cut = takeBatch([turn(1, text)]).batch[0].text;
    expect(cut).toHaveLength(MAX_TURN_CHARS - 1);
    expect(cut.endsWith("a")).toBe(true);
  });
});

describe("actionFor", () => {
  it.each([
    [200, "sent"],
    [207, "sent"],
    [429, "retry"],
    [500, "retry"],
    [503, "retry"],
    [null, "retry"],
    [400, "drop"],
    [401, "drop"],
    [403, "drop"],
    [422, "drop"],
  ])("status %s → %s", (status, action) => {
    expect(actionFor(status)).toBe(action);
  });
});

describe("backoffMs", () => {
  it("doubles from one second and never passes a minute", () => {
    const longest = (attempt: number) => backoffMs(attempt, () => 1);
    expect([0, 1, 2, 3].map(longest)).toEqual([1_000, 2_000, 4_000, 8_000]);
    expect(longest(6)).toBe(60_000);
    expect(longest(50)).toBe(60_000);
  });

  it("spreads retries between half and all of the wait", () => {
    expect(backoffMs(3, () => 0)).toBe(4_000);
    expect(backoffMs(3, () => 0.5)).toBe(6_000);
  });
});

describe("countResults", () => {
  const batch = [turn(1), turn(2), turn(3), turn(4)];

  it("counts each per-turn result", () => {
    const results = [
      { client_turn_id: "t1", result: "accepted" },
      { client_turn_id: "t2", result: "duplicate" },
      { client_turn_id: "t3", result: "rejected", reason: "blocked_pattern" },
      { client_turn_id: "t4", result: "accepted" },
    ];
    expect(countResults(batch, results)).toEqual({ accepted: 2, duplicate: 1, rejected: 1, missing: 0 });
  });

  it("counts a turn with no result, or an unknown one, as missing rather than accepted", () => {
    const results = [{ client_turn_id: "t1", result: "accepted" }, { client_turn_id: "t2", result: "queued" }, null];
    expect(countResults(batch, results)).toEqual({ accepted: 1, duplicate: 0, rejected: 0, missing: 3 });
  });

  it("counts everything as missing when the response has no result list", () => {
    expect(countResults(batch, { ok: true })).toEqual({ accepted: 0, duplicate: 0, rejected: 0, missing: 4 });
  });
});
