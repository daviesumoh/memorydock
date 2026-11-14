// When a message on the page is finished and may be captured, and when the
// page has drifted away from the contract.

export const STABLE_MS = 2_000;
export const IDLE_STOP_MS = 60_000;
export const DRIFT_AFTER_MS = 5 * 60_000;
export const DRIFT_MIN_MAIN_CHARS = 200;

// Bounds memory on very long conversations; the server treats a re-sent turn
// as a duplicate, so forgetting an old id costs one wasted request at most.
const MAX_EMITTED = 5_000;

export interface SeenMessage {
  // Stable for one message: its turn id.
  key: string;
  text: string;
}

// A message is final when its text has not changed for two seconds and nothing
// on the page is streaming. Each message is reported once.
export class FinalityTracker {
  private pending = new Map<string, { text: string; since: number }>();
  private emitted = new Set<string>();

  observe(messages: SeenMessage[], streaming: boolean, now: number): SeenMessage[] {
    const stillPending = new Map<string, { text: string; since: number }>();
    const final: SeenMessage[] = [];
    for (const message of messages) {
      if (this.emitted.has(message.key)) continue;
      const known = this.pending.get(message.key);
      const entry = known && known.text === message.text ? known : { text: message.text, since: now };
      if (!streaming && now - entry.since >= STABLE_MS) {
        final.push(message);
        this.remember(message.key);
      } else {
        stillPending.set(message.key, entry);
      }
    }
    // Messages no longer on the page (scrolled out of a virtualized thread)
    // start over if they come back.
    this.pending = stillPending;
    return final;
  }

  private remember(key: string) {
    this.emitted.add(key);
    if (this.emitted.size > MAX_EMITTED) {
      this.emitted.delete(this.emitted.values().next().value as string);
    }
  }
}

// Drift: the page clearly has content, but the contract has matched no message
// for five minutes. Once reported it stays until a new contract revision.
export class DriftDetector {
  private unmatchedSince: number | null = null;
  private drifted = false;

  observe(mainTextLength: number, matchedMessages: number, now: number): boolean {
    if (this.drifted) return true;
    if (matchedMessages > 0 || mainTextLength < DRIFT_MIN_MAIN_CHARS) {
      this.unmatchedSince = null;
      return false;
    }
    this.unmatchedSince ??= now;
    this.drifted = now - this.unmatchedSince >= DRIFT_AFTER_MS;
    return this.drifted;
  }

  reset() {
    this.unmatchedSince = null;
    this.drifted = false;
  }
}
