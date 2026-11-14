# The gateway image. Built from the repository root:
#   docker build -f infra/Dockerfile .

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so code changes don't re-download them.
COPY pyproject.toml uv.lock ./
COPY packages/memorydock_core/pyproject.toml packages/memorydock_core/pyproject.toml
COPY services/gateway/pyproject.toml services/gateway/pyproject.toml
RUN uv sync --frozen --no-dev --package memorydock-gateway --no-install-workspace
COPY packages packages
COPY services services
RUN uv sync --frozen --no-dev --package memorydock-gateway --no-editable

FROM python:3.12-slim
RUN useradd --system --uid 10001 --no-create-home memorydock
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER memorydock
EXPOSE 8080
# Fly's proxy terminates TLS and sets the forwarded headers.
CMD ["uvicorn", "--factory", "memorydock_gateway.app:create_app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
