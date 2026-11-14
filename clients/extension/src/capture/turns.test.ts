import { describe, expect, it } from "vitest";

import { clientTurnId, nextSeq, normalizeText, stopMarker } from "./turns.ts";

describe("clientTurnId", () => {
  it("uses the page's message id when there is one", async () => {
    expect(await clientTurnId("cnv_1", "user", "hello world", "msg-42")).toBe("msg-42");
  });

  // Expected digests computed separately with Python's hashlib.
  it("otherwise hashes conversation, role and text", async () => {
    expect(await clientTurnId("cnv_1", "user", "hello world", null)).toBe(
      "sha256:57c6bc7ee048f001e0ac8e6dbd67f75d396d5925b029b4ee0c56735c667e66b0", // pragma: allowlist secret
    );
    expect(await clientTurnId("cnv_1", "assistant", "hello world", null)).toBe(
      "sha256:9efbb316f87e3a9b36d45c8d620870fdc6eac8d070fb871091200657b984df82", // pragma: allowlist secret
    );
  });

  it("gives the same id however the page wraps or pads the text", async () => {
    const plain = await clientTurnId("cnv_1", "user", "hello world", null);
    expect(await clientTurnId("cnv_1", "user", "  hello\n   world \n", null)).toBe(plain);
  });

  it("gives different ids in different conversations", async () => {
    expect(await clientTurnId("cnv_2", "user", "hello world", null)).not.toBe(
      await clientTurnId("cnv_1", "user", "hello world", null),
    );
  });
});

describe("normalizeText", () => {
  it("treats composed and decomposed characters as the same text", () => {
    expect(normalizeText("café")).toBe(normalizeText("café"));
  });
});

describe("nextSeq", () => {
  it("counts from 1 separately for each conversation", () => {
    const counters: Record<string, number> = {};
    expect([nextSeq(counters, "a"), nextSeq(counters, "a"), nextSeq(counters, "b"), nextSeq(counters, "a")]).toEqual([1, 2, 1, 3]);
  });
});

describe("stopMarker", () => {
  it("is an empty marker turn with a stop kind", async () => {
    const marker = await stopMarker("cnv_1", 7, new Date("2026-11-14T12:00:00.000Z"));
    expect(marker).toMatchObject({ conversation_id: "cnv_1", seq: 7, role: "marker", kind: "stop", text: "", ts: "2026-11-14T12:00:00.000Z" });
  });

  it("has a different id for each idle period", async () => {
    const now = new Date();
    expect((await stopMarker("cnv_1", 7, now)).client_turn_id).not.toBe((await stopMarker("cnv_1", 9, now)).client_turn_id);
  });
});
