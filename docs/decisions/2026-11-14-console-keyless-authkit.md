# Console runs AuthKit without a WorkOS API key

Date: 2026-11-14

## Context

The console's environment was planned to hold `WORKOS_API_KEY` alongside the client id, cookie password and redirect URI. `@workos-inc/authkit-nextjs` 4.6 supports a public-client mode: without an API key it still handles sign-in, the callback, session refresh in the proxy, `withAuth` and `signOut`, using PKCE with the verifier held in an HttpOnly cookie. Only WorkOS management calls (feature-flag runtime client, API key validation, organization lookups) need the key.

The console makes no management calls. User emails are fetched by the gateway, which already holds the key.

## Decision

The console has no `WORKOS_API_KEY`. Its environment is `WORKOS_CLIENT_ID`, `WORKOS_COOKIE_PASSWORD`, `NEXT_PUBLIC_WORKOS_REDIRECT_URI` and `GATEWAY_URL`.

## Consequences

- One fewer secret on Vercel and on each laptop, and a leaked console environment cannot be used against the WorkOS management API.
- The WorkOS SDK reads `WORKOS_API_KEY` from the process environment on its own, so the variable must stay out of every console env source, or the console silently stops being keyless.
- If the console later needs a management call, it goes through a gateway route instead of adding the key here.
