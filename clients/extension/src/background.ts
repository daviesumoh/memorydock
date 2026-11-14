import { captureState } from "./capture-state.ts";
import { authorizeUrl, codeFromRedirect, exchangeCode, OAuthError, refreshTokens, type OAuthSettings } from "./auth/oauth.ts";
import { challengeFor, createVerifier, randomToken } from "./auth/pkce.ts";
import { TokenStore } from "./auth/token-store.ts";
import { allowedFromContentScript, parseMessage, type ExtensionMessage, type Reply } from "./messages.ts";

declare const GATEWAY_URL: string;
declare const AUTHKIT_DOMAIN: string;
declare const CLIENT_ID: string;

const GATEWAY_TIMEOUT_MS = 10_000;

const settings: OAuthSettings = {
  authkitDomain: new URL(AUTHKIT_DOMAIN),
  clientId: CLIENT_ID,
  redirectUri: chrome.identity.getRedirectURL(),
  // Tokens are bound to the MCP resource; /v1 accepts the same token.
  resource: `${GATEWAY_URL.replace(/\/+$/, "")}/mcp`,
};

// storage.local is readable by content scripts unless restricted, and it holds
// the refresh token. Older Chrome versions reject the call; say so and go on.
chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }).catch(() => {
  console.warn("memorydock: could not restrict storage.local to extension pages");
});

const tokens = new TokenStore(chrome.storage.session, chrome.storage.local, (refreshToken) =>
  refreshTokens(settings, refreshToken),
);

async function signIn(): Promise<Reply> {
  const verifier = createVerifier();
  const state = randomToken();
  let redirectedTo: string | undefined;
  try {
    redirectedTo = await chrome.identity.launchWebAuthFlow({
      url: authorizeUrl(settings, await challengeFor(verifier), state),
      interactive: true,
    });
  } catch {
    // Closing the window and a failed page load both land here.
    return { ok: false, error: "sign_in_cancelled" };
  }
  if (!redirectedTo) return { ok: false, error: "sign_in_cancelled" };
  const code = codeFromRedirect(settings, redirectedTo, state);
  await tokens.save(await exchangeCode(settings, code, verifier));
  return { ok: true };
}

async function account(): Promise<Reply> {
  const accessToken = await tokens.accessToken();
  if (!accessToken) return { ok: true, email: null };
  let response: Response;
  try {
    response = await fetch(`${GATEWAY_URL.replace(/\/+$/, "")}/v1/me`, {
      headers: { authorization: `Bearer ${accessToken}`, accept: "application/json" },
      signal: AbortSignal.timeout(GATEWAY_TIMEOUT_MS),
    });
  } catch {
    return { ok: false, error: "gateway_unreachable" };
  }
  const body: unknown = response.headers.get("content-type")?.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const code = (body as { error?: { code?: unknown } } | null)?.error?.code;
    return { ok: false, error: typeof code === "string" ? code : `http_${response.status}` };
  }
  const email = (body as { email?: unknown } | null)?.email;
  return { ok: true, email: typeof email === "string" ? email : null };
}

async function handle(message: ExtensionMessage): Promise<Reply> {
  switch (message.type) {
    case "get_status": {
      const signedIn = await tokens.isSignedIn();
      // No project is enabled until the mappings route exists, so capture
      // stays off; page facts come from the DOM contract once it is served.
      const page = message.page ?? { drift: false, temporaryChat: false, conversationId: null, projectId: null };
      const capture = captureState(page, { signedIn, tickedProjects: new Set(), mappedProjects: new Set() });
      return { ok: true, signedIn, capture };
    }
    case "get_account":
      return account();
    case "sign_in":
      return signIn();
    case "sign_out":
      await tokens.clear();
      return { ok: true };
  }
}

chrome.runtime.onMessage.addListener((raw, sender, sendResponse) => {
  // Only this extension's own pages and content scripts may ask.
  if (sender.id !== chrome.runtime.id) return false;
  const message = parseMessage(raw);
  if (!message) {
    sendResponse({ ok: false, error: "unknown_message" } satisfies Reply);
    return false;
  }
  // A message carrying a tab came from a content script on chatgpt.com.
  if (sender.tab && !allowedFromContentScript(message)) {
    sendResponse({ ok: false, error: "not_allowed" } satisfies Reply);
    return false;
  }
  handle(message)
    .then(sendResponse)
    .catch((error: unknown) => {
      sendResponse({ ok: false, error: error instanceof OAuthError ? error.code : "internal_error" } satisfies Reply);
    });
  // Keeps the channel open for the asynchronous reply.
  return true;
});
