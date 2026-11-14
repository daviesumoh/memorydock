import { afterEach, describe, expect, it, vi } from "vitest";

async function loadMockingEnabled() {
  vi.resetModules();
  return (await import("./mocking-gate")).mockingEnabled;
}

describe("mockingEnabled", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is on in development when the variable says so", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_API_MOCKING", "enabled");
    expect(await loadMockingEnabled()).toBe(true);
  });

  it("stays off in a production build even when the variable is set", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_MOCKING", "enabled");
    expect(await loadMockingEnabled()).toBe(false);
  });

  it.each(["", "true", "1", "Enabled"])("stays off for NEXT_PUBLIC_API_MOCKING=%j", async (value) => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_API_MOCKING", value);
    expect(await loadMockingEnabled()).toBe(false);
  });
});
