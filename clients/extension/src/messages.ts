// The fixed set of messages the background script answers. Content script and
// popup only ever ask; the background script alone will hold tokens.

export type ExtensionMessage = { type: "get_status" };

export type CaptureStatus =
  | { capturing: true }
  | { capturing: false; reason: "not_signed_in" };

export type MessageReply = { ok: true; status: CaptureStatus } | { ok: false; error: "unknown_message" };

export function isExtensionMessage(value: unknown): value is ExtensionMessage {
  return typeof value === "object" && value !== null && (value as { type?: unknown }).type === "get_status";
}

// Sign-in and capture are not built yet, so capture is always off.
export function currentStatus(): CaptureStatus {
  return { capturing: false, reason: "not_signed_in" };
}

export function handleMessage(message: unknown): MessageReply {
  if (!isExtensionMessage(message)) {
    return { ok: false, error: "unknown_message" };
  }
  return { ok: true, status: currentStatus() };
}

export function badgeText(status: CaptureStatus): string {
  if (status.capturing) return "● capturing";
  return "paused · not signed in";
}
