import { describe, expect, it } from "vitest";

import { DriftDetector, FinalityTracker } from "./finality.ts";

const message = (key: string, text: string) => ({ key, text });

describe("FinalityTracker", () => {
  it("reports a message once its text has been stable for two seconds", () => {
    const tracker = new FinalityTracker();
    expect(tracker.observe([message("m1", "hi")], false, 0)).toEqual([]);
    expect(tracker.observe([message("m1", "hi")], false, 1_999)).toEqual([]);
    expect(tracker.observe([message("m1", "hi")], false, 2_000)).toEqual([message("m1", "hi")]);
  });

  it("restarts the wait whenever the text changes", () => {
    const tracker = new FinalityTracker();
    tracker.observe([message("m1", "par")], false, 0);
    tracker.observe([message("m1", "partial")], false, 1_500);
    expect(tracker.observe([message("m1", "partial")], false, 3_000)).toEqual([]);
    expect(tracker.observe([message("m1", "partial")], false, 3_500)).toEqual([message("m1", "partial")]);
  });

  it("reports nothing while the page is streaming, however long the pause", () => {
    const tracker = new FinalityTracker();
    tracker.observe([message("m1", "thinking")], true, 0);
    expect(tracker.observe([message("m1", "thinking")], true, 10_000)).toEqual([]);
    expect(tracker.observe([message("m1", "thinking")], false, 10_001)).toEqual([message("m1", "thinking")]);
  });

  it("reports each message once, including after it scrolls away and back", () => {
    const tracker = new FinalityTracker();
    tracker.observe([message("m1", "hi")], false, 0);
    expect(tracker.observe([message("m1", "hi")], false, 2_000)).toHaveLength(1);
    expect(tracker.observe([], false, 3_000)).toEqual([]);
    expect(tracker.observe([message("m1", "hi")], false, 9_000)).toEqual([]);
  });

  it("starts the wait over for an unfinished message that left the page", () => {
    const tracker = new FinalityTracker();
    tracker.observe([message("m1", "hi")], false, 0);
    tracker.observe([], false, 1_000);
    expect(tracker.observe([message("m1", "hi")], false, 2_500)).toEqual([]);
    expect(tracker.observe([message("m1", "hi")], false, 4_500)).toHaveLength(1);
  });

  it("handles an empty page", () => {
    expect(new FinalityTracker().observe([], false, 0)).toEqual([]);
  });
});

describe("DriftDetector", () => {
  const FIVE_MINUTES = 5 * 60_000;

  it("reports drift after five minutes of content with no matched message", () => {
    const drift = new DriftDetector();
    expect(drift.observe(200, 0, 0)).toBe(false);
    expect(drift.observe(200, 0, FIVE_MINUTES - 1)).toBe(false);
    expect(drift.observe(200, 0, FIVE_MINUTES)).toBe(true);
  });

  it("does not count a page with under 200 characters, such as a new chat", () => {
    const drift = new DriftDetector();
    drift.observe(199, 0, 0);
    expect(drift.observe(199, 0, FIVE_MINUTES * 2)).toBe(false);
  });

  it("starts over when a message matches", () => {
    const drift = new DriftDetector();
    drift.observe(500, 0, 0);
    drift.observe(500, 1, FIVE_MINUTES - 1);
    expect(drift.observe(500, 0, FIVE_MINUTES)).toBe(false);
    expect(drift.observe(500, 0, FIVE_MINUTES * 2)).toBe(true);
  });

  it("stays drifted even if something matches later, until a new contract resets it", () => {
    const drift = new DriftDetector();
    drift.observe(500, 0, 0);
    drift.observe(500, 0, FIVE_MINUTES);
    expect(drift.observe(500, 3, FIVE_MINUTES + 1)).toBe(true);
    drift.reset();
    expect(drift.observe(500, 3, FIVE_MINUTES + 2)).toBe(false);
  });
});
