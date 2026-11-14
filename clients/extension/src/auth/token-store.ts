import { OAuthError, type TokenSet } from "./oauth.ts";

// The subset of chrome.storage.StorageArea this needs, so tests can pass a fake.
export interface StorageArea {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(key: string): Promise<void>;
}

export const REFRESH_BEFORE_EXPIRY_MS = 60_000;

const ACCESS_KEY = "auth.access";
const REFRESH_KEY = "auth.refresh";

interface StoredAccess {
  token: string;
  expiresAt: number;
}

export type Refresh = (refreshToken: string) => Promise<TokenSet>;

// The access token lives in session storage (cleared when the browser closes).
// The refresh token goes in the second area: local storage, restricted to
// extension pages, so sign-in survives a restart.
export class TokenStore {
  private inflight: Promise<string | null> | null = null;
  // Bumped by clear(), so a refresh that was already running when the user
  // signed out cannot write its tokens back afterwards.
  private generation = 0;
  private readonly session: StorageArea;
  private readonly local: StorageArea;
  private readonly refresh: Refresh;
  private readonly now: () => number;

  constructor(session: StorageArea, local: StorageArea, refresh: Refresh, now: () => number = Date.now) {
    this.session = session;
    this.local = local;
    this.refresh = refresh;
    this.now = now;
  }

  async save(tokens: TokenSet): Promise<void> {
    await this.session.set({ [ACCESS_KEY]: { token: tokens.accessToken, expiresAt: tokens.expiresAt } satisfies StoredAccess });
    await this.local.set({ [REFRESH_KEY]: tokens.refreshToken });
  }

  async clear(): Promise<void> {
    this.generation += 1;
    this.inflight = null;
    await this.session.remove(ACCESS_KEY);
    await this.local.remove(REFRESH_KEY);
  }

  async isSignedIn(): Promise<boolean> {
    return typeof (await this.local.get(REFRESH_KEY))[REFRESH_KEY] === "string";
  }

  // A usable access token, refreshed first if it expires within a minute, or
  // null when signed out. Concurrent callers share one refresh: refresh tokens
  // are single-use, so two parallel refreshes would invalidate each other.
  async accessToken(): Promise<string | null> {
    const stored = (await this.session.get(ACCESS_KEY))[ACCESS_KEY] as StoredAccess | undefined;
    if (stored && stored.expiresAt - this.now() > REFRESH_BEFORE_EXPIRY_MS) return stored.token;
    this.inflight ??= this.refreshNow().finally(() => {
      this.inflight = null;
    });
    return this.inflight;
  }

  private async refreshNow(): Promise<string | null> {
    const startedIn = this.generation;
    const refreshToken = (await this.local.get(REFRESH_KEY))[REFRESH_KEY];
    if (typeof refreshToken !== "string") return null;
    try {
      const tokens = await this.refresh(refreshToken);
      if (this.generation !== startedIn) return null;
      await this.save(tokens);
      return tokens.accessToken;
    } catch (error) {
      if (this.generation !== startedIn) return null;
      // AuthKit refusing the refresh token means the session is over. A network
      // failure does not, so the tokens stay and the caller sees the error.
      if (error instanceof OAuthError && error.code !== "network_error") {
        await this.clear();
        return null;
      }
      throw error;
    }
  }
}
