## What and why
Closes #

## How it was verified
<commands, tests, screenshots of the console where relevant>

## Checks
- [ ] make lint scan privacy test pass; console: pnpm typecheck lint test build
- [ ] Integration tests run locally against my dev database (if core/gateway/worker changed)
- [ ] Failure-path, concurrency and leak tests where they apply
- [ ] No secrets or content in logs; no AI attribution anywhere in this PR
- [ ] Generated files regenerated (openapi, schema types, lockfiles), not hand-edited
- [ ] If infra/atlas changed: setup script run, both roles regenerated and applied, role tests pass

## Shared areas touched
<policies/, infra/, core/repo/, auth, routing, openapi — or none>
