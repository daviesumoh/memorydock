// AuthKit authorization code flow for a public client: building the authorize
// URL, checking the redirect, and the token requests. No chrome.* here, so it
// is testable on its own.

export const SCOPES = "openid profile email offline_access";
const TOKEN_TIMEOUT_MS = 10_000;

export interface OAuthSettings {
  authkitDomain: URL;
  clientId: string;
  redirectUri: string;
  // The MCP resource the token is bound to (its audience).
  resource: string;
}

export interface TokenSet {
  accessToken: string;
  refreshToken: string;
  // Milliseconds since the epoch.
  expiresAt: number;
}

export class OAuthError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "OAuthError";
    this.code = code;
  }
}

function endpoint(settings: OAuthSettings, path: string): string {
  return new URL(path, settings.authkitDomain).toString();
}

export function authorizeUrl(settings: OAuthSettings, challenge: string, state: string): string {
  const url = new URL(endpoint(settings, "/oauth2/authorize"));
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: settings.clientId,
    redirect_uri: settings.redirectUri,
    scope: SCOPES,
    resource: settings.resource,
    code_challenge: challenge,
    code_challenge_method: "S256",
    state,
  }).toString();
  return url.toString();
}

// Returns the authorization code from the redirect, after checking that it is
// the redirect we asked for: our redirect URI, our state, and AuthKit as issuer.
export function codeFromRedirect(settings: OAuthSettings, redirectedTo: string, expectedState: string): string {
  const url = new URL(redirectedTo);
  if (`${url.origin}${url.pathname}` !== settings.redirectUri) {
    throw new OAuthError("redirect_mismatch", "Sign-in returned to an unexpected address");
  }
  const params = url.searchParams;
  if (params.get("state") !== expectedState) {
    throw new OAuthError("state_mismatch", "Sign-in response did not match the request");
  }
  // RFC 9207: AuthKit names itself, which rules out a response from another server.
  const issuer = params.get("iss");
  if (issuer !== null && issuer !== settings.authkitDomain.origin) {
    throw new OAuthError("issuer_mismatch", "Sign-in response came from an unexpected server");
  }
  const error = params.get("error");
  if (error) {
    throw new OAuthError(error, params.get("error_description") ?? "Sign-in was not completed");
  }
  const code = params.get("code");
  if (!code) throw new OAuthError("missing_code", "Sign-in response had no authorization code");
  return code;
}

function parseTokenResponse(body: unknown, now: number): TokenSet {
  const fields = body as { access_token?: unknown; refresh_token?: unknown; expires_in?: unknown };
  if (
    typeof fields?.access_token !== "string" ||
    typeof fields.refresh_token !== "string" ||
    typeof fields.expires_in !== "number" ||
    fields.expires_in <= 0
  ) {
    throw new OAuthError("invalid_token_response", "AuthKit returned an incomplete token response");
  }
  return {
    accessToken: fields.access_token,
    refreshToken: fields.refresh_token,
    expiresAt: now + fields.expires_in * 1000,
  };
}

async function tokenRequest(settings: OAuthSettings, form: Record<string, string>, now: () => number): Promise<TokenSet> {
  let response: Response;
  try {
    response = await fetch(endpoint(settings, "/oauth2/token"), {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
      body: new URLSearchParams({ client_id: settings.clientId, ...form }),
      signal: AbortSignal.timeout(TOKEN_TIMEOUT_MS),
    });
  } catch {
    throw new OAuthError("network_error", "Could not reach AuthKit");
  }
  const contentType = response.headers.get("content-type") ?? "";
  const body: unknown = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const code = typeof (body as { error?: unknown } | null)?.error === "string" ? (body as { error: string }).error : `http_${response.status}`;
    throw new OAuthError(code, "AuthKit refused the token request");
  }
  return parseTokenResponse(body, now());
}

export function exchangeCode(settings: OAuthSettings, code: string, verifier: string, now = Date.now) {
  return tokenRequest(
    settings,
    { grant_type: "authorization_code", code, code_verifier: verifier, redirect_uri: settings.redirectUri },
    now,
  );
}

export function refreshTokens(settings: OAuthSettings, refreshToken: string, now = Date.now) {
  return tokenRequest(settings, { grant_type: "refresh_token", refresh_token: refreshToken, resource: settings.resource }, now);
}
