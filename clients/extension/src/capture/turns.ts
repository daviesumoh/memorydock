// Turn identity and ordering.

export type TurnRole = "user" | "assistant" | "marker";

export interface Turn {
  client_turn_id: string;
  conversation_id: string;
  seq: number;
  role: TurnRole;
  kind?: "stop";
  text: string;
  // ISO 8601.
  ts: string;
  meta: { title?: string; chatgpt_project?: string };
}

// Whitespace differs between renders of the same message (line wrapping,
// trailing newlines), so it is collapsed before hashing.
export function normalizeText(text: string): string {
  return text.normalize("NFC").replace(/\s+/g, " ").trim();
}

async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

// The page's own message id when it has one, otherwise a hash of what the
// message is. Never its position: ChatGPT lazy-loads and virtualizes long
// threads, so positions shift and the same message would be stored twice. Two
// identical messages in one conversation share an id, which is acceptable.
export async function clientTurnId(
  conversationId: string,
  role: TurnRole,
  text: string,
  messageId: string | null,
): Promise<string> {
  if (messageId) return messageId;
  return `sha256:${await sha256Hex(`${conversationId}\0${role}\0${normalizeText(text)}`)}`;
}

// Per-conversation order, kept by the background script. Ordering only.
export function nextSeq(counters: Record<string, number>, conversationId: string): number {
  const seq = (counters[conversationId] ?? 0) + 1;
  counters[conversationId] = seq;
  return seq;
}

// Ends a segment after the conversation has been idle.
export async function stopMarker(conversationId: string, seq: number, now: Date): Promise<Turn> {
  return {
    client_turn_id: await clientTurnId(conversationId, "marker", `stop ${seq}`, null),
    conversation_id: conversationId,
    seq,
    role: "marker",
    kind: "stop",
    text: "",
    ts: now.toISOString(),
    meta: {},
  };
}
