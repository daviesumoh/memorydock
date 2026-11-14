# 2026-11-14

- Created the repository, public with a protected `main` (see `docs/decisions/2026-11-14-public-repository.md`).
- Added the uv workspace with dev tooling only. Packages join the workspace as they are created, so `uv sync --all-packages` stays meaningful from the start.
- Added the privacy check and secret scan. Findings print file, line and kind; we never echo the matched value, since CI logs on a public repo are public too. Identifiers to block are read from `.env` and `.local/` at runtime, which keeps the list itself out of the tree.
- The Makefile only has targets that work today. Atlas, gateway, worker, CLI, OpenAPI and deploy targets come with the issues that add their scripts.
- `.env.example` waits until code reads its first variable.
