// Forwards a browser request to the gateway with the session's access token.
// The token is added here, server-side, so it never reaches the browser.

// Headers the browser may send on to the gateway. Cookies stay behind: the
// session cookie belongs to the console, and the gateway authenticates by
// bearer token only.
const FORWARDED_REQUEST_HEADERS = ["accept", "content-type", "if-match", "last-event-id"];

// Set-Cookie is left out so the gateway can never set cookies on the console's origin.
const FORWARDED_RESPONSE_HEADERS = [
  "cache-control",
  "content-type",
  "etag",
  "retry-after",
  "x-request-id",
];

// Covers the wait for response headers only. Streams (SSE) stay open after that.
export const UPSTREAM_HEADERS_TIMEOUT_MS = 15_000;

export type ProxyErrorCode =
  | "not_signed_in"
  | "not_found"
  | "gateway_unreachable"
  | "gateway_timeout";

export interface ForwardOptions {
  request: Request;
  path: string[];
  accessToken: string | null;
  gatewayUrl: URL;
  headersTimeoutMs?: number;
}

function errorResponse(status: number, code: ProxyErrorCode, message: string, requestId: string) {
  return Response.json(
    { code, message, request_id: requestId },
    { status, headers: { "cache-control": "no-store", "x-request-id": requestId } },
  );
}

// Only /v1 is reachable, and dot segments are refused so a crafted path cannot
// climb out of it after URL normalization.
export function isForwardablePath(path: string[]): boolean {
  if (path.length < 2 || path[0] !== "v1") return false;
  return path.every((segment) => segment !== "" && segment !== "." && segment !== "..");
}

export function buildUpstreamUrl(gatewayUrl: URL, path: string[], search: string): URL {
  const upstream = new URL(gatewayUrl);
  const basePath = upstream.pathname.replace(/\/+$/, "");
  upstream.pathname = `${basePath}/${path.map(encodeURIComponent).join("/")}`;
  upstream.search = search;
  return upstream;
}

export async function forwardToGateway({
  request,
  path,
  accessToken,
  gatewayUrl,
  headersTimeoutMs = UPSTREAM_HEADERS_TIMEOUT_MS,
}: ForwardOptions): Promise<Response> {
  const requestId = crypto.randomUUID();

  if (!accessToken) {
    return errorResponse(401, "not_signed_in", "Sign in to use the console", requestId);
  }
  if (!isForwardablePath(path)) {
    return errorResponse(404, "not_found", "No such gateway route", requestId);
  }

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  headers.set("authorization", `Bearer ${accessToken}`);
  headers.set("x-request-id", requestId);

  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), headersTimeoutMs);
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const upstreamUrl = buildUpstreamUrl(gatewayUrl, path, new URL(request.url).search);

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Node's fetch requires this to stream a request body.
      ...(hasBody ? { duplex: "half" } : {}),
      redirect: "manual",
      // The browser closing the connection also cancels the upstream call.
      signal: AbortSignal.any([request.signal, timeout.signal]),
    } as RequestInit);
  } catch {
    if (request.signal.aborted) {
      // The browser has gone; nobody reads this response.
      return errorResponse(502, "gateway_unreachable", "The request was cancelled", requestId);
    }
    if (timeout.signal.aborted) {
      console.error("gateway proxy: timed out waiting for headers", { requestId });
      return errorResponse(504, "gateway_timeout", "The gateway did not respond in time", requestId);
    }
    console.error("gateway proxy: gateway unreachable", { requestId });
    return errorResponse(502, "gateway_unreachable", "The gateway could not be reached", requestId);
  } finally {
    clearTimeout(timer);
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value !== null) responseHeaders.set(name, value);
  }
  if (!responseHeaders.has("x-request-id")) responseHeaders.set("x-request-id", requestId);
  if (!responseHeaders.has("cache-control")) responseHeaders.set("cache-control", "no-store");

  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}
