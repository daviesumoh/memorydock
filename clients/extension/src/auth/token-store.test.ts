import { describe, expect, it, vi } from "vitest";

import { OAuthError, type TokenSet } from "./oauth.ts";
import { REFRESH_BEFORE_EXPIRY_MS, TokenStore, type StorageArea } from "./token-store.ts";

function memoryArea(): StorageArea & { data: Map<string, unknown> } {
  const data = new Map<string, unknown>();
  return {
    data,
    get: async (key) => (data.has(key) ? { [key]: data.get(key) } : {}),
    set: async (items) => {
      for (const [key, value] of Object.entries(items)) data.set(key, value);
    },
    remove: async (key) => {
      data.delete(key);
    },
  };
}

const NOW = 1_000_000;
const tokens = (n: number, expiresIn = 300_000): TokenSet => ({
  accessToken: `at${n}`,
  refreshToken: `rt${n}`,
  expiresAt: NOW + expiresIn,
});

function setup(refresh = vi.fn(async (): Promise<TokenSet> => tokens(2))) {
  const session = memoryArea();
  const local = memoryArea();
  const store = new TokenStore(session, local, refresh, () => NOW);
  return { store, session, local, refresh };
}

describe("TokenStore", () => {
  it("keeps the access token in session storage and only the refresh token in local storage", async () => {
    const { store, session, local } = setup();
    await store.save(tokens(1));

    expect(JSON.stringify([...session.data.values()])).toContain("at1");
    expect(JSON.stringify([...local.data.values()])).not.toContain("at1");
    expect(JSON.stringify([...local.data.values()])).toContain("rt1");
  });

  it("returns the stored token while it has more than a minute left", async () => {
    const { store, refresh } = setup();
    await store.save(tokens(1, REFRESH_BEFORE_EXPIRY_MS + 1));
    expect(await store.accessToken()).toBe("at1");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("refreshes a token with a minute or less left, and stores the new pair", async () => {
    const { store, refresh, local } = setup();
    await store.save(tokens(1, REFRESH_BEFORE_EXPIRY_MS));

    expect(await store.accessToken()).toBe("at2");
    expect(refresh).toHaveBeenCalledWith("rt1");
    expect([...local.data.values()]).toContain("rt2");
  });

  it("refreshes once for concurrent callers, since a refresh token works only once", async () => {
    let release!: () => void;
    const refresh = vi.fn(
      () =>
        new Promise<TokenSet>((resolve) => {
          release = () => resolve(tokens(2));
        }),
    );
    const { store } = setup(refresh);
    await store.save(tokens(1, 0));

    const callers = Promise.all([store.accessToken(), store.accessToken(), store.accessToken()]);
    await vi.waitFor(() => expect(refresh).toHaveBeenCalled());
    release();

    expect(await callers).toEqual(["at2", "at2", "at2"]);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("signs out when AuthKit refuses the refresh token", async () => {
    const { store, session, local } = setup(vi.fn(async () => Promise.reject(new OAuthError("invalid_grant", "used"))));
    await store.save(tokens(1, 0));

    expect(await store.accessToken()).toBeNull();
    expect(await store.isSignedIn()).toBe(false);
    expect(session.data.size).toBe(0);
    expect(local.data.size).toBe(0);
  });

  it("stays signed in through a network failure and reports it", async () => {
    const { store } = setup(vi.fn(async () => Promise.reject(new OAuthError("network_error", "offline"))));
    await store.save(tokens(1, 0));

    await expect(store.accessToken()).rejects.toMatchObject({ code: "network_error" });
    expect(await store.isSignedIn()).toBe(true);
  });

  it("returns null without calling AuthKit when never signed in", async () => {
    const { store, refresh } = setup();
    expect(await store.accessToken()).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("does not sign back in when a refresh finishes after sign-out", async () => {
    let release!: () => void;
    const refresh = vi.fn(
      () =>
        new Promise<TokenSet>((resolve) => {
          release = () => resolve(tokens(2));
        }),
    );
    const { store, session, local } = setup(refresh);
    await store.save(tokens(1, 0));

    const pending = store.accessToken();
    await vi.waitFor(() => expect(refresh).toHaveBeenCalled());
    await store.clear();
    release();

    expect(await pending).toBeNull();
    expect(await store.isSignedIn()).toBe(false);
    expect(session.data.size + local.data.size).toBe(0);
  });

  it("forgets both tokens on sign-out", async () => {
    const { store, session, local } = setup();
    await store.save(tokens(1));
    await store.clear();
    expect(session.data.size + local.data.size).toBe(0);
  });
});
