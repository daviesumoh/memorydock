# memorydock

Shared, governed memory and coordination for AI agents, on MongoDB Atlas.

Claude Code, Codex, the Claude app and any other MCP client connect to one gateway. A fact told
to one of them can be recalled by the others. Every call is tied to a signed-in person and checked
by policy before it runs, and every change is written to a hash-chained audit log.

## Features

- **One MCP gateway for every agent.** Streamable HTTP MCP at `/mcp`, signed in through WorkOS
  AuthKit. Clients are told on connect to recall before answering and to remember what the user
  states, without being asked.
- **Governed memory.** `remember` stores a memory in a scope the server works out (personal,
  project, team or org). `recall` runs hybrid search, meaning plus exact words, and returns a
  ranked, token-budgeted context block with memory ids to cite.
- **Forget that really forgets.** `forget_memory` clears the text, the search text and the
  entities on the memory and on every past version, drops it from the search indexes, and blocks
  the same content from being stored again.
- **Conversation capture.** `capture_conversation` distills a conversation into a few memories with
  LangMem, and each one goes through the same checks as `remember`.
- **File leases.** `acquire_lease`, `release_lease` and `list_leases` let agents claim a file in a
  repository before editing it, so two agents don't edit the same file at once.
- **Policy as code.** Cedar policies decide every action. They are stored in Atlas and reloaded
  without a restart.
- **Hash-chained audit log.** Each event carries the hash of the one before it, over a canonical
  JSON form (RFC 8785), so any edit or deletion breaks the chain. The chain can be verified from
  the console or a script.
- **Session control.** Each person gets one agent session per client per day. An admin or the owner
  can pause a session (reads only) or revoke it (nothing).
- **Console.** A Next.js app to browse, create and forget memories, see their version history, read
  and verify the audit log, and pause, resume or revoke sessions.

## Architecture

```
 Claude Code    Codex    Claude app          Browser
      \           |          /                   |
       \          |         /              Console (Next.js, Vercel)
        MCP over HTTP + AuthKit token       same-origin proxy adds the token
                  |                                 |
                  v                                 v
   +----------------------------------------------------------------+
   |  Gateway (FastAPI + FastMCP, Fly.io)                            |
   |                                                                 |
   |  /mcp  agent tools          /v1  console API                    |
   |        |                          |                             |
   |  token check  ->  identity  ->  Cedar policy  ->  core service  |
   |  (AuthKit JWKS,   (users by     (hot-reloaded     (memory,      |
   |   audience)        sub, cache)   from Atlas)       recall,      |
   |                                                    leases,      |
   |                                                    sessions,    |
   |                                                    distill)     |
   +---------------------------------------------------------+------+
                                                             |
                     one transaction per write: record + version + audit event
                                                             v
   +----------------------------------------------------------------+
   |  MongoDB Atlas                                                  |
   |  memories, memory_versions, audit_log, agent_sessions, leases,  |
   |  users, orgs, teams, projects, policies, forget_blocklist       |
   |                                                                 |
   |  Automated Embedding (voyage-4)  ->  memory_semantic (vector)   |
   |  Atlas Search                    ->  memory_lexical (text)      |
   +----------------------------------------------------------------+
```

### Code layout

| Path | What it holds |
| --- | --- |
| `services/gateway/` | FastAPI app, MCP server and tools, console routes, token verification |
| `packages/memorydock_core/` | Everything the gateway calls: identity, policy, memory, recall, leases, sessions, distiller, audit, database access |
| `policies/` | Cedar schema and policies |
| `infra/atlas/` | Collection validators, indexes and search index definitions |
| `infra/Dockerfile`, `infra/fly.toml` | Gateway image and Fly.io config |
| `console/` | Next.js console |
| `clients/extension/` | Chrome extension (see its README) |
| `scripts/` | Atlas setup, policy publish, audit verification, seeding, deploy, repository checks |
| `docs/decisions/` | Decision records |

### How a request runs

1. **Sign-in.** The client gets an AuthKit access token for `<gateway>/mcp`. The gateway checks
   the signature, issuer, expiry and audience. The token carries no email, org or roles; the
   gateway looks the person up in its own `users` collection by `sub`, linking by email on first
   sign-in, and caches the result. The client label (for example `claude-code`) comes from the
   token's `client_id`.
2. **Session.** The gateway finds or opens the person's session for that client and day.
3. **Policy.** Each tool call becomes a Cedar request: who, which action, which resource. A paused
   or revoked session, a scope the person isn't in, or an org-wide write that needs approval is
   refused here with a clear error code.
4. **Remember.** The server resolves the scope and sets trust from how the memory arrived
   (console, stated by the user, or inferred by the agent). It hashes normalized content, so an
   exact duplicate returns the existing memory and forgotten content is refused. The memory, its
   first version and the audit event are written in one transaction.
5. **Recall.** Atlas embeds the question and runs vector search and text search in one
   `$rankFusion` stage (meaning weighted 1.0, exact words 0.6). Both branches are pre-filtered by
   org, the scopes the person can read and status, so other orgs' memories never enter the search.
   The gateway then re-checks the live records, rescores by trust, recency, scope and confidence,
   drops weak matches, asks Cedar about the survivors in one batch, and packs them into a
   `<memory_context>` block within the token budget. The recall itself is audited.
6. **Forget.** Clears content on the memory and its versions, marks it forgotten, adds the content
   hash to the blocklist and writes an audit event with a hash of what changed. Calling it again is
   a no-op.
7. **Leases.** `acquire_lease` normalizes the repository and path and inserts an active lease. A
   partial unique index allows only one active lease per file, so a second agent is told who holds
   it. Each new lease gets a higher fence number. Leases don't expire; only the holder releases.

## Quick start

Requires Python 3.12, `uv`, Node with `pnpm`, an Atlas M10 cluster or larger with Automated
Embedding, and a WorkOS AuthKit environment.

```
git clone <repo-url> && cd memorydock
cp .env.example .env       # fill in the values
make setup                 # install the Python workspace
make check-env             # confirm the settings load
make atlas-setup           # collections, validators, indexes, search indexes
make policy-dev            # publish and activate the Cedar policies
make gateway               # gateway on http://127.0.0.1:8000
```

Add the gateway to an MCP client, for example Claude Code:

```
claude mcp add --transport http memorydock http://127.0.0.1:8000/mcp
```

Run the console:

```
pnpm install
cp console/.env.example console/.env.local
pnpm --filter memorydock-console dev     # http://localhost:3000
```

`make demo-seed` creates the demo orgs, project and users (see the Makefile for its arguments).

## MCP tools

| Tool | What it does |
| --- | --- |
| `whoami` | The signed-in person, their org, session, client and readable scopes |
| `remember` | Store a memory in a resolved scope |
| `recall` | Ranked memories and a context block for a question |
| `forget_memory` | Forget a memory everywhere it is stored |
| `capture_conversation` | Distill a conversation into memories |
| `acquire_lease` | Claim a file in a repository before editing it |
| `release_lease` | Release a file you hold |
| `list_leases` | Active leases in a repository |

## Console API

All routes are under `/v1` and need a bearer token. `docs/openapi.json` is the full contract.

| Route | What it does |
| --- | --- |
| `GET /me` | The signed-in person |
| `GET /memories`, `POST /memories` | List or create memories |
| `GET /memories/{id}`, `GET /memories/{id}/versions` | One memory and its history |
| `POST /memories/{id}/forget` | Forget a memory |
| `GET /audit`, `GET /audit/verify` | Read and verify the audit chain |
| `GET /sessions` | Sessions you can see |
| `POST /sessions/{id}/pause`, `/resume`, `/revoke` | Change a session's state |

## Configuration

Every setting comes from an environment variable. `.env.example` lists each one with a comment and
no real values. The main ones:

| Variable | Purpose |
| --- | --- |
| `GATEWAY_BASE_URL` | Public URL of the gateway; tokens must be issued for `<this>/mcp` |
| `MONGODB_URI`, `MONGODB_DB` | Atlas connection and database |
| `AUTOEMBED_MODEL` | Embedding model for Automated Embedding |
| `AUTHKIT_DOMAIN`, `WORKOS_CLIENT_ID`, `WORKOS_API_KEY` | Sign-in and the first-sign-in email lookup |
| `CONSOLE_ORIGIN`, `EXTENSION_ORIGIN` | Origins allowed to call `/v1` |
| `RECALL_TOKEN_BUDGET` | Size of the recall context block |
| `OPENAI_API_KEY` | OpenAI access for the distiller; `capture_conversation` is off when unset |
| `DISTILL_MODEL` | Model the distiller uses |

## Development

```
make hooks     # commit-msg and pre-commit hooks
make lint      # ruff format check, ruff, mypy
make scan      # secret scan, unused code, unused dependencies
make privacy   # personal data and attribution check over tracked files
make openapi   # regenerate docs/openapi.json and the console's API types
```

## Testing

```
make test                 # unit tests
make test-integration     # needs MONGODB_URI_ADMIN; each run uses its own test database
make verify-preview       # checks embedding, rankFusion and forget purge on a live cluster
```

Integration tests run against Atlas Local in CI. Atlas Local has no embedding model, so
search-dependent behaviour is checked with `make verify-preview` against a real cluster.

## Deployment

The gateway runs on Fly.io from `infra/Dockerfile` and `infra/fly.toml`. Secrets are set with
`fly secrets set`; `make deploy` deploys from a clean checkout, stamps the commit and waits for
`/readyz`. The console deploys to Vercel with `GATEWAY_URL` pointing at the gateway.

## Status

Built and tested:

- Gateway with AuthKit sign-in, identity linking and per-client sessions
- `remember`, `recall`, `forget_memory`, `capture_conversation`
- File leases over MCP
- Cedar policies with hot reload, and the hash-chained audit log with verification
- Console: memories, audit log and sessions
- Fly.io deployment of the gateway and Vercel deployment of the console

## Security

Report security issues privately through GitHub security advisories on this repository, not in
public issues.
