import { describe, expect, it } from "vitest";

import { badgeText, handleMessage } from "./messages.ts";

describe("handleMessage", () => {
  it("reports capture as off while sign-in is not built", () => {
    expect(handleMessage({ type: "get_status" })).toEqual({
      ok: true,
      status: { capturing: false, reason: "not_signed_in" },
    });
  });

  it.each([
    [undefined],
    [null],
    ["get_status"],
    [{}],
    [{ type: "get_token" }],
    [{ type: "GET_STATUS" }],
  ])("refuses %j as an unknown message", (message) => {
    expect(handleMessage(message)).toEqual({ ok: false, error: "unknown_message" });
  });
});

describe("badgeText", () => {
  it("says why capture is paused", () => {
    expect(badgeText({ capturing: false, reason: "not_signed_in" })).toBe("paused · not signed in");
  });

  it("marks active capture", () => {
    expect(badgeText({ capturing: true })).toBe("● capturing");
  });
});
