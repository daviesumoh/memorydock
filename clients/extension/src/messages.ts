// The fixed set of messages the background script answers. Content scripts run
// inside chatgpt.com, so they may only ask for status; signing in and out and
// reading the account are for the extension's own pages.

import type { CaptureBlock, CaptureState, PageFacts } from "./capture-state.ts";

export type ExtensionMessage =
  | { type: "get_status"; page: PageFacts | null }
  | { type: "get_account" }
  | { type: "sign_in" }
  | { type: "sign_out" };

export type StatusReply = { ok: true; signedIn: boolean; capture: CaptureState };
export type AccountReply = { ok: true; email: string | null };
export type ErrorReply = { ok: false; error: string };
export type Reply = StatusReply | AccountReply | { ok: true } | ErrorReply;

function isPageFacts(value: unknown): value is PageFacts {
  const facts = value as Partial<PageFacts> | null;
  return (
    typeof facts === "object" &&
    facts !== null &&
    typeof facts.drift === "boolean" &&
    typeof facts.temporaryChat === "boolean" &&
    (facts.conversationId === null || typeof facts.conversationId === "string") &&
    (facts.projectId === null || typeof facts.projectId === "string")
  );
}

export function parseMessage(value: unknown): ExtensionMessage | null {
  const type = (value as { type?: unknown } | null)?.type;
  switch (type) {
    case "get_status": {
      const page = (value as { page?: unknown }).page ?? null;
      return page === null || isPageFacts(page) ? { type, page } : null;
    }
    case "get_account":
    case "sign_in":
    case "sign_out":
      return { type };
    default:
      return null;
  }
}

export function allowedFromContentScript(message: ExtensionMessage): boolean {
  return message.type === "get_status";
}

const BLOCK_TEXT: Record<CaptureBlock, string> = {
  drift: "layout changed",
  temporary_chat: "temporary chat",
  not_signed_in: "not signed in",
  no_conversation: "no conversation",
  not_in_project: "not in a project",
  project_not_enabled: "project not enabled",
};

export function badgeText(capture: CaptureState): string {
  if (capture.capturing) return "● capturing";
  return `paused · ${BLOCK_TEXT[capture.reason]}`;
}
