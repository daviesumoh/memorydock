# MCP access tokens carry no email, org or roles

## Context

We signed in to the local gateway from Claude Code through WorkOS AuthKit (Staging) and logged
the shape of the access token it received, without values. The token has these claims and no
others: `aud`, `auth_time`, `client_id`, `exp`, `iat`, `iss`, `jti`, `sid`, `sub`.

- `aud` is the resource indicator, `<GATEWAY_BASE_URL>/mcp`.
- `client_id` is the client's metadata document URL (CIMD), not a registered client id.
- There is no `email`, `org_id` or `roles` claim.
- The token lives for 300 seconds.

## Decision

- The gateway verifies the signature, issuer, expiry and an explicit audience of
  `<GATEWAY_BASE_URL>/mcp`. A token minted for another resource is rejected.
- Identity, organization and roles come from our own `users` collection, keyed by `sub`. Nothing
  about authorization is read from the token beyond `sub` and `client_id`.
- The first time a `sub` is seen, the gateway asks the WorkOS user API for that user's email and
  links it to exactly one unlinked user with that email. No match is `unknown_user`; more than
  one is `ambiguous_user`. Both are refused. Later requests look up by `sub` only.
- Resolved principals are cached for `IDENTITY_CACHE_SECONDS`, so the WorkOS call and the
  database lookups don't run on every request.
- The client label comes from the token's `client_id`: a fixed table of known metadata URLs
  (Claude Code maps to `claude-code`), then the console and extension client ids; anything else
  is labelled `other`.
- Each user gets one MCP agent session per client per day. The gateway is stateless over HTTP,
  so there is no connection to hang a session on, and we don't rely on `sid` staying stable
  across token refreshes.

## Consequences

- Adding someone means seeding a user row with their email before their first sign-in.
  `scripts/seed_dev.py` does this for dev databases.
- Removing someone from an org takes effect within the cache window.
- If WorkOS later adds org or role claims, we still won't trust them for authorization.
