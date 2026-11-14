import { describe, expect, it } from "vitest";

import { allowedFromContentScript, badgeText, parseMessage } from "./messages.ts";

const facts = { drift: false, temporaryChat: false, conversationId: "cnv_1", projectId: null };

describe("parseMessage", () => {
  it.each([
    [{ type: "get_status", page: facts }],
    [{ type: "get_status", page: null }],
    [{ type: "get_account" }],
    [{ type: "sign_in" }],
    [{ type: "sign_out" }],
  ])("accepts %j", (message) => {
    expect(parseMessage(message)).toEqual(message);
  });

  it("treats a status request without page facts as having none", () => {
    expect(parseMessage({ type: "get_status" })).toEqual({ type: "get_status", page: null });
  });

  it.each([
    [undefined],
    [null],
    ["get_status"],
    [{}],
    [{ type: "get_token" }],
    [{ type: "GET_STATUS" }],
    [{ type: "get_status", page: { drift: "no" } }],
    [{ type: "get_status", page: { ...facts, conversationId: 7 } }],
  ])("refuses %j", (message) => {
    expect(parseMessage(message)).toBeNull();
  });
});

describe("allowedFromContentScript", () => {
  it("lets a content script ask for status and nothing else", () => {
    expect(allowedFromContentScript({ type: "get_status", page: null })).toBe(true);
    expect(allowedFromContentScript({ type: "get_account" })).toBe(false);
    expect(allowedFromContentScript({ type: "sign_in" })).toBe(false);
    expect(allowedFromContentScript({ type: "sign_out" })).toBe(false);
  });
});

describe("badgeText", () => {
  it("says why capture is paused", () => {
    expect(badgeText({ capturing: false, reason: "not_signed_in" })).toBe("paused · not signed in");
    expect(badgeText({ capturing: false, reason: "drift" })).toBe("paused · layout changed");
  });

  it("marks active capture", () => {
    expect(badgeText({ capturing: true, projectId: "proj_1" })).toBe("● capturing");
  });
});
