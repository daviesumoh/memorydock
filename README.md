# memorydock

Shared, governed memory and coordination for AI agents, on MongoDB Atlas.

Every agent you connect (Claude Code, Codex CLI, the Claude app, ChatGPT) reads from and writes to one memory store through one gateway. Every operation is tied to an identity, checked by policy before it runs, and written to a hash-chained audit log.

This repository is at the start of its build. The sections below describe what exists today; see Status.

## Features

Planned primitives:

- Memory: facts, decisions, preferences, procedures and findings captured from agent conversations, distilled, scoped and recalled automatically.
- Coordination: leases on shared resources (repo files first), an inbox between agent sessions, and human-confirmed approvals.
- Task ledger: durable, verified multi-step task state against GitHub that survives crashes and handoffs.

None of these is built yet.

## Quick start

Not runnable yet. Once the gateway exists this will be:

```
git clone <repo-url> && cd memorydock
cp .env.example .env
make setup
make atlas-setup
make gateway
memorydock login
```

## Architecture

Python gateway (FastAPI + FastMCP) and worker on MongoDB Atlas, a Next.js console, a CLI with agent hooks, and a Chrome extension for ChatGPT capture. `docs/ARCHITECTURE.md` will hold the details once the gateway exists.

## Configuration

All settings come from environment variables. `.env.example` will list every variable the code reads, one comment per variable, with no real values.

## Development

Requires Python 3.12 and `uv`.

```
make setup     # install the workspace
make hooks     # install the commit-msg and pre-commit hooks
make lint      # ruff format check, ruff, mypy
make scan      # secret scan, unused code, unused dependencies
make privacy   # personal data and attribution check over tracked files
```

## Testing

```
make test
```

## Deployment

Not set up yet. The gateway and worker will run on Fly.io and the console on Vercel.

## Status

Working:

- Repository tooling: lint, secret scan, privacy check and commit-message check (verified by `make lint scan privacy test` and CI).

Partial:

- None.

Not built:

- Gateway, worker, CLI, console, Chrome extension, policies and audit log.
- Email notifications and digests.
- Slack, Linear, Notion and Jira adapters.
- Scheduled integrity checks (verification is on demand).
- Shared-folder file-hash staleness checks.
- Distiller-proposed categories.
- Telling apart same-named people.
- Category retention enforcement.
- Symbol-level leases.
- Database-per-tenant and crypto-shredding.
- Custom LangGraph client agents and mobile clients.
- ChatGPT desktop-app capture and a "Save to memory" button in the extension.

## Security

Report security issues privately through GitHub security advisories on this repository rather than in public issues.
