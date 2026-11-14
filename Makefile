.PHONY: setup hooks lint scan privacy test openapi gateway check-env policy-dev atlas-setup atlas-roles verify-preview test-integration

PY_SOURCES := packages services scripts tests
# deptry runs per package directory so each package is checked against its own dependencies.
DEPTRY_DIRS := $(dir $(wildcard packages/*/pyproject.toml services/*/pyproject.toml clients/cli/pyproject.toml))

setup:
	uv sync --all-packages

hooks:
	git config core.hooksPath scripts/git-hooks

lint:
	uv run ruff format --check $(PY_SOURCES)
	uv run ruff check $(PY_SOURCES)
	uv run mypy $(PY_SOURCES)

scan:
	uv run python scripts/scan_secrets.py
	uv run vulture $(PY_SOURCES) vulture_allowlist.py --min-confidence 80
	@for d in $(DEPTRY_DIRS); do (cd $$d && uv run deptry .) || exit 1; done

privacy:
	uv run python scripts/privacy_check.py

test:
	uv run pytest tests/unit

# Regenerates the API spec and the console types built from it; commit both.
openapi:
	uv run python scripts/export_openapi.py
	cd console && pnpm gen:api

# Local gateway on 127.0.0.1:8000 with reload; run it in your own terminal.
gateway:
	uv run uvicorn --factory memorydock_gateway.app:create_app --host 127.0.0.1 --port 8000 --reload

# Publishes policies/ to your own database and activates it without a prompt.
policy-dev:
	uv run python scripts/policy_publish.py --activate --yes

check-env:
	uv run python scripts/check_env.py

atlas-setup:
	uv run python -u scripts/atlas_setup.py --wait

# Preview only; apply with: uv run python scripts/atlas_roles.py --apply
atlas-roles:
	uv run python scripts/atlas_roles.py

# Live-cluster check of the search features recall depends on; writes docs/verify_preview_results.json.
verify-preview:
	uv run python -u scripts/verify_preview.py

# Needs MONGODB_URI_ADMIN; each run creates and drops its own memorydock_test_<random> database.
test-integration:
	uv run pytest tests/integration
