import { describe, expect, it } from "vitest";

import { BUNDLED_CONTRACT, capturableRoles, pageFacts, parseContract, type DomContract } from "./contract.ts";

// A made-up page structure for these tests, not chatgpt.com's.
const wire = {
  schema_version: 1,
  revision: 3,
  user_message: "[data-test-role=user]",
  assistant_message: "[data-test-role=assistant]",
  message_id_attribute: "data-test-id",
  streaming_indicator: ".test-streaming",
  composer: "#test-composer",
  title: "title",
  conversation_path: "/chat/([a-z0-9-]+)$",
  project_path: "^/project/([a-z0-9-]+)/",
  temporary_chat_param: "temp",
};
const contract = parseContract(wire) as DomContract;

describe("parseContract", () => {
  it("reads every field", () => {
    expect(contract).toMatchObject({ revision: 3, userMessage: "[data-test-role=user]", temporaryChatParam: "temp" });
  });

  it.each([
    ["an unknown schema version", { ...wire, schema_version: 2 }],
    ["no schema version", { ...wire, schema_version: undefined }],
    ["a missing field", { ...wire, composer: undefined }],
    ["a non-string field", { ...wire, title: 7 }],
    ["a negative revision", { ...wire, revision: -1 }],
    ["a path pattern that is not a regular expression", { ...wire, conversation_path: "/c/(" }],
    ["null", null],
    ["a string", "contract"],
  ])("rejects %s", (_label, value) => {
    expect(parseContract(value)).toBeNull();
  });
});

describe("capturableRoles", () => {
  it("captures nothing with the bundled contract, where no field is verified", () => {
    expect(capturableRoles(BUNDLED_CONTRACT)).toEqual([]);
  });

  it("captures both roles once everything they need is verified", () => {
    expect(capturableRoles(contract)).toEqual(["user", "assistant"]);
  });

  it("leaves out assistant messages without a streaming indicator", () => {
    expect(capturableRoles({ ...contract, streamingIndicator: "" })).toEqual(["user"]);
  });

  it.each(["conversationPath", "projectPath", "temporaryChatParam"] as const)(
    "captures nothing while %s is unverified, since opt-in could not be checked",
    (field) => {
      expect(capturableRoles({ ...contract, [field]: "" })).toEqual([]);
    },
  );
});

describe("pageFacts", () => {
  it("reads the conversation and project from the path", () => {
    expect(pageFacts(contract, new URL("https://chatgpt.com/project/p-1/chat/c-9"), false)).toEqual({
      drift: false,
      temporaryChat: false,
      conversationId: "c-9",
      projectId: "p-1",
    });
  });

  it("reports a chat outside a project and a page with no conversation", () => {
    expect(pageFacts(contract, new URL("https://chatgpt.com/chat/c-9"), false).projectId).toBeNull();
    expect(pageFacts(contract, new URL("https://chatgpt.com/"), false).conversationId).toBeNull();
  });

  it.each([
    ["?temp=true", true],
    ["?temp", true],
    ["?temp=false", false],
    ["", false],
  ])("temporary chat for %j is %s", (query, expected) => {
    expect(pageFacts(contract, new URL(`https://chatgpt.com/chat/c-9${query}`), false).temporaryChat).toBe(expected);
  });

  it("knows nothing about the page with the bundled contract", () => {
    expect(pageFacts(BUNDLED_CONTRACT, new URL("https://chatgpt.com/chat/c-9?temp=true"), true)).toEqual({
      drift: true,
      temporaryChat: false,
      conversationId: null,
      projectId: null,
    });
  });
});
