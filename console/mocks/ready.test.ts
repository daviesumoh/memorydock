import { afterEach, describe, expect, it, vi } from "vitest";

async function loadReady() {
  vi.resetModules();
  return import("./ready");
}

function stubMocking(nodeEnv: string, flag: string) {
  vi.stubEnv("NODE_ENV", nodeEnv);
  vi.stubEnv("NEXT_PUBLIC_API_MOCKING", flag);
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("mockingEnabled", () => {
  it("is on in development when the variable says so", async () => {
    stubMocking("development", "enabled");
    expect((await loadReady()).mockingEnabled).toBe(true);
  });

  it("stays off in a production build even when the variable is set", async () => {
    stubMocking("production", "enabled");
    expect((await loadReady()).mockingEnabled).toBe(false);
  });

  it.each(["", "true", "1", "Enabled"])("stays off for NEXT_PUBLIC_API_MOCKING=%j", async (value) => {
    stubMocking("development", value);
    expect((await loadReady()).mockingEnabled).toBe(false);
  });
});

describe("waitForMocks", () => {
  it("resolves at once when mocking is off, so real calls are not delayed", async () => {
    stubMocking("development", "");
    const { waitForMocks } = await loadReady();
    await expect(waitForMocks()).resolves.toBeUndefined();
  });

  it("holds gateway calls until the worker reports ready", async () => {
    stubMocking("development", "enabled");
    const { waitForMocks, markWorkerReady } = await loadReady();

    let released = false;
    const waiting = waitForMocks().then(() => {
      released = true;
    });
    await Promise.resolve();
    expect(released).toBe(false);

    markWorkerReady();
    await waiting;
    expect(released).toBe(true);
  });
});
