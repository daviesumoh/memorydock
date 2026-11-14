import { describe, expect, it } from "vitest";

import { captureState, type PageFacts, type UserFacts } from "./capture-state.ts";

const page: PageFacts = { drift: false, temporaryChat: false, conversationId: "cnv_1", projectId: "proj_1" };
const user: UserFacts = {
  signedIn: true,
  tickedProjects: new Set(["proj_1"]),
  mappedProjects: new Set(["proj_1"]),
};

describe("captureState", () => {
  it("captures only a ticked, mapped project for a signed-in user", () => {
    expect(captureState(page, user)).toEqual({ capturing: true, projectId: "proj_1" });
  });

  it.each<[string, Partial<PageFacts>, Partial<UserFacts>, string]>([
    ["layout drift", { drift: true }, {}, "drift"],
    ["a temporary chat", { temporaryChat: true }, {}, "temporary_chat"],
    ["a signed-out user", {}, { signedIn: false }, "not_signed_in"],
    ["no conversation yet", { conversationId: null }, {}, "no_conversation"],
    ["a chat outside any project", { projectId: null }, {}, "not_in_project"],
    ["a project nobody ticked", {}, { tickedProjects: new Set() }, "project_not_enabled"],
    ["a ticked project with no mapping yet", {}, { mappedProjects: new Set() }, "project_not_enabled"],
    ["a mapping for a different project", { projectId: "proj_2" }, {}, "project_not_enabled"],
  ])("does not capture %s", (_label, pageChange, userChange, reason) => {
    expect(captureState({ ...page, ...pageChange }, { ...user, ...userChange })).toEqual({ capturing: false, reason });
  });

  // When several things block capture, the reason is the first in the spec's order.
  it.each<[Partial<PageFacts>, Partial<UserFacts>, string]>([
    [{ drift: true, temporaryChat: true }, { signedIn: false }, "drift"],
    [{ temporaryChat: true, projectId: null }, { signedIn: false }, "temporary_chat"],
    [{ conversationId: null, projectId: null }, { signedIn: false }, "not_signed_in"],
    [{ conversationId: null, projectId: null }, {}, "no_conversation"],
    [{ projectId: null }, { tickedProjects: new Set() }, "not_in_project"],
  ])("reports the first block in order: %j %j → %s", (pageChange, userChange, reason) => {
    expect(captureState({ ...page, ...pageChange }, { ...user, ...userChange })).toEqual({ capturing: false, reason });
  });
});
