// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { BUNDLED_CONTRACT, capturableRoles, EMPTY_CONTRACT, messageId, pageFacts, parseContract, type DomContract } from "./contract.ts";

// A made-up page structure for these tests, not chatgpt.com's.
const wire = {
  schema_version: 1,
  revision: 3,
  user_message: "[data-test-role=user]",
  assistant_message: "[data-test-role=assistant]",
  user_message_id_attribute: "data-test-ids",
  assistant_message_id_attribute: "data-test-reply",
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
  it("captures nothing with an empty contract", () => {
    expect(capturableRoles(EMPTY_CONTRACT)).toEqual([]);
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

  it("knows nothing about the page with an empty contract", () => {
    expect(pageFacts(EMPTY_CONTRACT, new URL("https://chatgpt.com/chat/c-9?temp=true"), true)).toEqual({
      drift: true,
      temporaryChat: false,
      conversationId: null,
      projectId: null,
    });
  });
});

// Page shapes as observed on chatgpt.com, with made-up ids.
describe("the bundled contract", () => {
  const conversation = "0f8fad5b-d9cb-469f-a165-70867728950e";
  const facts = (path: string) => pageFacts(BUNDLED_CONTRACT, new URL(`https://chatgpt.com${path}`), false);

  it("captures both roles", () => {
    expect(capturableRoles(BUNDLED_CONTRACT)).toEqual(["user", "assistant"]);
  });

  it("survives a round trip through its wire form", () => {
    const c = BUNDLED_CONTRACT;
    const parsed = parseContract({
      schema_version: 1,
      revision: c.revision,
      user_message: c.userMessage,
      assistant_message: c.assistantMessage,
      user_message_id_attribute: c.userMessageIdAttribute,
      assistant_message_id_attribute: c.assistantMessageIdAttribute,
      streaming_indicator: c.streamingIndicator,
      composer: c.composer,
      title: c.title,
      conversation_path: c.conversationPath,
      project_path: c.projectPath,
      temporary_chat_param: c.temporaryChatParam,
    });
    expect(parsed).toEqual(c);
  });

  it("reads a project conversation, leaving the project's slug out of its id", () => {
    expect(facts(`/g/g-p-6a1f09c2-launch-plan/c/${conversation}`)).toMatchObject({
      conversationId: conversation,
      projectId: "g-p-6a1f09c2",
      temporaryChat: false,
    });
  });

  it("reads a conversation outside a project", () => {
    expect(facts(`/c/${conversation}`)).toMatchObject({ conversationId: conversation, projectId: null });
  });

  it("sees a temporary chat", () => {
    expect(facts(`/c/${conversation}?temporary-chat=true`).temporaryChat).toBe(true);
  });

  it("finds no conversation on a project's home page or a new chat", () => {
    expect(facts("/g/g-p-6a1f09c2-launch-plan/project").conversationId).toBeNull();
    expect(facts("/").conversationId).toBeNull();
  });
});

describe("messageId", () => {
  const page = (html: string) => {
    document.body.innerHTML = html;
    return document.body;
  };

  it("reads a user message's id from the wrapper above it", () => {
    const body = page('<div data-chatgpt-search-message-ids="m-1"><div><div data-user-message-bubble="true">hi</div></div></div>');
    expect(messageId(BUNDLED_CONTRACT, "user", body.querySelector(BUNDLED_CONTRACT.userMessage)!)).toBe("m-1");
  });

  it("reads an assistant message's id from the message itself, not the wrapper's list", () => {
    const body = page('<div data-chatgpt-search-message-ids="m-2 m-3"><div data-response-body="m-3">hello</div></div>');
    expect(messageId(BUNDLED_CONTRACT, "assistant", body.querySelector(BUNDLED_CONTRACT.assistantMessage)!)).toBe("m-3");
  });

  it.each(["m-1 m-2", "m-1,m-2", ""])("treats %j as no id", (value) => {
    const body = page(`<div data-chatgpt-search-message-ids="${value}"><div data-user-message-bubble="true">hi</div></div>`);
    expect(messageId(BUNDLED_CONTRACT, "user", body.querySelector(BUNDLED_CONTRACT.userMessage)!)).toBeNull();
  });

  it("gives no id with an empty contract", () => {
    const body = page('<div data-response-body="m-3">hello</div>');
    expect(messageId(EMPTY_CONTRACT, "assistant", body.firstElementChild!)).toBeNull();
  });
});
