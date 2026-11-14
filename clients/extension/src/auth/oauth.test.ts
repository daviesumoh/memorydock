import { afterEach, describe, expect, it, vi } from "vitest";

import { authorizeUrl, codeFromRedirect, exchangeCode, OAuthError, refreshTokens, type OAuthSettings } from "./oauth.ts";

const settings: OAuthSettings = {
  authkitDomain: new URL("https://example.authkit.app"),
  clientId: "client_ext_test",
  redirectUri: "https://ohlflggckmdbbaooockgncafhecpjboc.chromiumapp.org/",
  resource: "https://gateway.example.com/mcp",
};

const redirect = (params: Record<string, string>) =>
  `${settings.redirectUri}?${new URLSearchParams(params).toString()}`;

function oauthError(fn: () => unknown): OAuthError {
  try {
    fn();
  } catch (error) {
    if (error instanceof OAuthError) return error;
    throw error;
  }
  throw new Error("expected an OAuthError");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("authorizeUrl", () => {
  it("asks AuthKit for a PKCE code bound to the MCP resource", () => {
    const url = new URL(authorizeUrl(settings, "challenge123", "state123"));
    expect(`${url.origin}${url.pathname}`).toBe("https://example.authkit.app/oauth2/authorize");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      response_type: "code",
      client_id: "client_ext_test",
      redirect_uri: settings.redirectUri,
      scope: "openid profile email offline_access",
      resource: "https://gateway.example.com/mcp",
      code_challenge: "challenge123",
      code_challenge_method: "S256",
      state: "state123",
    });
  });
});

describe("codeFromRedirect", () => {
  it("returns the code when state and issuer match", () => {
    expect(codeFromRedirect(settings, redirect({ code: "c1", state: "s1", iss: "https://example.authkit.app" }), "s1")).toBe("c1");
  });

  it("accepts a response without iss, which RFC 9207 leaves optional for older servers", () => {
    expect(codeFromRedirect(settings, redirect({ code: "c1", state: "s1" }), "s1")).toBe("c1");
  });

  it.each([
    ["a different state", redirect({ code: "c1", state: "forged" }), "state_mismatch"],
    ["no state", redirect({ code: "c1" }), "state_mismatch"],
    ["another issuer", redirect({ code: "c1", state: "s1", iss: "https://evil.example" }), "issuer_mismatch"],
    ["another redirect address", "https://evil.example/?code=c1&state=s1", "redirect_mismatch"],
    ["an error from AuthKit", redirect({ error: "access_denied", state: "s1" }), "access_denied"],
    ["no code", redirect({ state: "s1" }), "missing_code"],
  ])("refuses %s", (_label, url, code) => {
    expect(oauthError(() => codeFromRedirect(settings, url, "s1")).code).toBe(code);
  });

  it("checks state before trusting an error, so a forged error is reported as a mismatch", () => {
    expect(oauthError(() => codeFromRedirect(settings, redirect({ error: "access_denied", state: "forged" }), "s1")).code).toBe(
      "state_mismatch",
    );
  });
});

describe("token requests", () => {
  function stubTokenEndpoint(response: Response | Error) {
    const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => {
      if (response instanceof Error) throw response;
      return response;
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("exchanges the code with the verifier and no client secret", async () => {
    const fetchMock = stubTokenEndpoint(
      Response.json({ access_token: "at", refresh_token: "rt", expires_in: 300, token_type: "Bearer" }),
    );
    const tokens = await exchangeCode(settings, "code1", "verifier1", () => 1_000);

    expect(tokens).toEqual({ accessToken: "at", refreshToken: "rt", expiresAt: 301_000 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://example.authkit.app/oauth2/token");
    expect(Object.fromEntries(new URLSearchParams(init.body as URLSearchParams))).toEqual({
      client_id: "client_ext_test",
      grant_type: "authorization_code",
      code: "code1",
      code_verifier: "verifier1",
      redirect_uri: settings.redirectUri,
    });
  });

  it("refreshes for the same resource", async () => {
    const fetchMock = stubTokenEndpoint(Response.json({ access_token: "at2", refresh_token: "rt2", expires_in: 300 }));
    await refreshTokens(settings, "rt1");
    const body = Object.fromEntries(new URLSearchParams(fetchMock.mock.calls[0][1].body as URLSearchParams));
    expect(body).toMatchObject({ grant_type: "refresh_token", refresh_token: "rt1", resource: settings.resource });
  });

  it.each([
    ["no refresh token", { access_token: "at", expires_in: 300 }],
    ["no expiry", { access_token: "at", refresh_token: "rt" }],
    ["a zero expiry", { access_token: "at", refresh_token: "rt", expires_in: 0 }],
  ])("refuses a response with %s", async (_label, body) => {
    stubTokenEndpoint(Response.json(body));
    await expect(exchangeCode(settings, "c", "v")).rejects.toMatchObject({ code: "invalid_token_response" });
  });

  it("reports AuthKit's error code when it refuses", async () => {
    stubTokenEndpoint(Response.json({ error: "invalid_grant" }, { status: 400 }));
    await expect(refreshTokens(settings, "used")).rejects.toMatchObject({ code: "invalid_grant" });
  });

  it("reports a network failure as network_error", async () => {
    stubTokenEndpoint(new TypeError("fetch failed"));
    await expect(refreshTokens(settings, "rt")).rejects.toMatchObject({ code: "network_error" });
  });
});
