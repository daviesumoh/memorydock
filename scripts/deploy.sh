#!/usr/bin/env bash
# Deploy the gateway to Fly from a clean checkout of main, stamping the commit into /readyz.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "deploy: commit or stash your changes first" >&2
  exit 1
fi
sha="$(git rev-parse --short=12 HEAD)"
fly deploy --config infra/fly.toml --dockerfile infra/Dockerfile --env "GIT_SHA=${sha}" \
  --wait-timeout 300 .
url="$(sed -n 's/^ *GATEWAY_BASE_URL = "\(.*\)"/\1/p' infra/fly.toml)"
curl -fsS "${url}/readyz"
echo
