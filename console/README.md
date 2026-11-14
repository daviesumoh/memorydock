# memorydock console

Next.js (App Router) console for memorydock. It signs people in with WorkOS AuthKit and reaches the gateway only through a same-origin proxy, so access tokens stay on the server.

## Setup

```
pnpm install                     # from the repository root
cp console/.env.example console/.env.local
```

Fill in `console/.env.local`. The WorkOS environment needs these application settings:

- Redirect URI: `http://localhost:3000/callback`
- Initiate login URI: `http://localhost:3000/sign-in`
- A default Sign-out URI, which `signOut()` redirects to

The console runs AuthKit as a public PKCE client, so it has no WorkOS API key (see `docs/decisions/2026-11-14-console-keyless-authkit.md`).

## Running

```
pnpm --filter memorydock-console dev
```

## How requests reach the gateway

Browser code calls `/api/gateway/v1/...`. The route handler reads the session's access token, adds it as a bearer token and forwards the request to `<GATEWAY_URL>/v1/...`.

- Only `/v1` paths are forwarded; anything else gets a 404 from the console.
- POST, PUT, PATCH and DELETE must come from the console's own pages: `Sec-Fetch-Site` has to be `same-origin`, or, for a browser that does not send it, `Origin` has to match. The session cookie is `SameSite=Lax`, which would still allow a page on another localhost port or a sibling subdomain to send it.
- Request and response headers pass through fixed allow-lists. Cookies are never sent to the gateway, and `Set-Cookie` from the gateway is dropped.
- Response bodies stream, so server-sent events work through the proxy.
- Only JSON and `text/event-stream` responses are passed on. Proxied responses are served from the console's origin, so a gateway response that a browser could render (HTML, SVG, an untyped body) is refused with a 502 instead. Every proxy response carries `X-Content-Type-Options: nosniff` and a sandboxing `Content-Security-Policy`.
- The proxy waits 15 seconds for response headers. Streams stay open after that.
- Proxy errors use the shape `{ code, message, request_id }`, with codes `not_signed_in` (401), `cross_origin_request` (403), `not_found` (404), `gateway_unreachable` (502), `gateway_bad_response` (502) and `gateway_timeout` (504).

## Checks

```
pnpm typecheck
pnpm lint
pnpm test          # unit tests (Vitest)
pnpm build
pnpm test:e2e      # builds and starts the app, then runs the Playwright smoke tests
```

The smoke tests use placeholder WorkOS values and never contact WorkOS or a gateway. They check that a signed-out visit redirects to AuthKit with PKCE and that the proxy answers 401 without a session.
