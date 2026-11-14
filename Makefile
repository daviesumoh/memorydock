.PHONY: setup hooks lint scan privacy test

PY_SOURCES := scripts tests
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
	uv run vulture $(PY_SOURCES) --min-confidence 80
	@for d in $(DEPTRY_DIRS); do uv run deptry $$d || exit 1; done

privacy:
	uv run python scripts/privacy_check.py

test:
	uv run pytest tests/unit
