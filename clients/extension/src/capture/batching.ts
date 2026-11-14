// Splitting queued turns into requests the gateway accepts, and what to do
// with each response.

import type { Turn } from "./turns.ts";

// The gateway takes 50 turns, 100,000 characters per turn and 1 MB per body.
// Batches stay well inside all three.
export const MAX_BATCH_TURNS = 20;
export const MAX_TURN_CHARS = 100_000;
export const MAX_BODY_BYTES = 900_000;
export const FLUSH_AFTER_MS = 2_000;
export const MAX_BACKOFF_MS = 60_000;

const encoder = new TextEncoder();

function withinTurnLimit(turn: Turn): Turn {
  if (turn.text.length <= MAX_TURN_CHARS) return turn;
  let text = turn.text.slice(0, MAX_TURN_CHARS);
  // Do not end on half of a surrogate pair.
  const last = text.charCodeAt(text.length - 1);
  if (last >= 0xd800 && last <= 0xdbff) text = text.slice(0, -1);
  return { ...turn, text };
}

// Takes turns from the front of the queue, in order, up to the count and size
// limits. An oversized turn is cut to the limit rather than blocking the queue.
export function takeBatch(queue: readonly Turn[]): { batch: Turn[]; rest: Turn[] } {
  const batch: Turn[] = [];
  let bytes = 0;
  for (const queued of queue) {
    if (batch.length === MAX_BATCH_TURNS) break;
    const turn = withinTurnLimit(queued);
    const size = encoder.encode(JSON.stringify(turn)).length;
    if (batch.length > 0 && bytes + size > MAX_BODY_BYTES) break;
    batch.push(turn);
    bytes += size;
  }
  return { batch, rest: queue.slice(batch.length) };
}

export type SendAction = "sent" | "retry" | "drop";

// Rate limits, server errors and network failures (status null) are worth
// retrying. Any other 4xx will fail the same way again, so the batch is dropped.
export function actionFor(status: number | null): SendAction {
  if (status === null || status === 429 || status >= 500) return "retry";
  if (status >= 200 && status < 300) return "sent";
  return "drop";
}

// Exponential from one second, capped at a minute, with jitter so tabs that
// failed together do not retry together.
export function backoffMs(attempt: number, random: () => number = Math.random): number {
  const ceiling = Math.min(MAX_BACKOFF_MS, 1_000 * 2 ** Math.min(attempt, 16));
  return Math.round(ceiling / 2 + (random() * ceiling) / 2);
}

export interface TurnResult {
  client_turn_id: string;
  result: "accepted" | "duplicate" | "rejected";
  reason?: string;
}

export type ResultCounts = Record<TurnResult["result"] | "missing", number>;

// Counts only, never content. A turn the gateway did not answer for is counted
// as missing rather than assumed accepted.
export function countResults(batch: readonly Turn[], results: unknown): ResultCounts {
  const counts: ResultCounts = { accepted: 0, duplicate: 0, rejected: 0, missing: 0 };
  const byId = new Map<string, string>();
  if (Array.isArray(results)) {
    for (const entry of results as Partial<TurnResult>[]) {
      if (typeof entry?.client_turn_id === "string" && typeof entry.result === "string") {
        byId.set(entry.client_turn_id, entry.result);
      }
    }
  }
  for (const turn of batch) {
    const result = byId.get(turn.client_turn_id);
    if (result === "accepted" || result === "duplicate" || result === "rejected") counts[result] += 1;
    else counts.missing += 1;
  }
  return counts;
}
