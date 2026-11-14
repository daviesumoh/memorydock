// The selector contract: everything the extension knows about chatgpt.com's
// page structure. A field stays empty until it has been checked on the live
// site, and an empty field switches off whatever depends on it. Selectors are
// never guessed.

import type { PageFacts } from "../capture-state.ts";

export const SCHEMA_VERSION = 1;

export interface DomContract {
  // Bumped by the gateway whenever a field changes; capture resumes after
  // drift only on a higher revision.
  revision: number;
  userMessage: string;
  assistantMessage: string;
  messageIdAttribute: string;
  streamingIndicator: string;
  composer: string;
  title: string;
  // Regular expressions over location.pathname; group 1 is the id.
  conversationPath: string;
  projectPath: string;
  temporaryChatParam: string;
}

// Nothing is verified yet, so the bundled default captures nothing.
export const BUNDLED_CONTRACT: DomContract = {
  revision: 0,
  userMessage: "",
  assistantMessage: "",
  messageIdAttribute: "",
  streamingIndicator: "",
  composer: "",
  title: "",
  conversationPath: "",
  projectPath: "",
  temporaryChatParam: "",
};

const STRING_FIELDS = {
  user_message: "userMessage",
  assistant_message: "assistantMessage",
  message_id_attribute: "messageIdAttribute",
  streaming_indicator: "streamingIndicator",
  composer: "composer",
  title: "title",
  conversation_path: "conversationPath",
  project_path: "projectPath",
  temporary_chat_param: "temporaryChatParam",
} as const;

function compiles(pattern: string): boolean {
  try {
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
}

// Returns null for anything that is not a contract this build understands:
// another schema version, a missing or non-string field, or a path pattern
// that is not a regular expression.
export function parseContract(json: unknown): DomContract | null {
  const raw = json as Record<string, unknown> | null;
  if (typeof raw !== "object" || raw === null || raw.schema_version !== SCHEMA_VERSION) return null;
  if (!Number.isInteger(raw.revision) || (raw.revision as number) < 0) return null;

  const contract: DomContract = { ...BUNDLED_CONTRACT, revision: raw.revision as number };
  for (const [wireName, field] of Object.entries(STRING_FIELDS)) {
    const value = raw[wireName];
    if (typeof value !== "string") return null;
    contract[field] = value;
  }
  if (!compiles(contract.conversationPath) || !compiles(contract.projectPath)) return null;
  return contract;
}

export type CapturableRole = "user" | "assistant";

// Capture needs to know which conversation and project a page is and whether
// it is a temporary chat; without those three it could capture a chat the
// user never opted in. Assistant messages also need the streaming indicator,
// or a pause in a streaming reply would look final.
export function capturableRoles(contract: DomContract): CapturableRole[] {
  if (!contract.conversationPath || !contract.projectPath || !contract.temporaryChatParam) return [];
  const roles: CapturableRole[] = [];
  if (contract.userMessage) roles.push("user");
  if (contract.assistantMessage && contract.streamingIndicator) roles.push("assistant");
  return roles;
}

function firstGroup(pattern: string, pathname: string): string | null {
  if (!pattern) return null;
  return new RegExp(pattern).exec(pathname)?.[1] ?? null;
}

export function pageFacts(contract: DomContract, url: URL, drift: boolean): PageFacts {
  const flag = contract.temporaryChatParam ? url.searchParams.get(contract.temporaryChatParam) : null;
  return {
    drift,
    temporaryChat: flag !== null && flag !== "false",
    conversationId: firstGroup(contract.conversationPath, url.pathname),
    projectId: firstGroup(contract.projectPath, url.pathname),
  };
}
