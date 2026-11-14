"""Which client a token came from, derived from its OAuth client_id, never from the request."""

from __future__ import annotations

from memorydock_core.models.common import SessionClient

# Client ID Metadata Document URLs that MCP clients present to AuthKit.
CIMD_LABELS: dict[str, SessionClient] = {
    "https://claude.ai/oauth/claude-code-client-metadata": "claude-code",
}


def client_label(
    client_id: str, *, console_client_id: str, extension_client_id: str
) -> SessionClient:
    if client_id in CIMD_LABELS:
        return CIMD_LABELS[client_id]
    if console_client_id and client_id == console_client_id:
        return "console"
    if extension_client_id and client_id == extension_client_id:
        return "chatgpt"
    # Dynamically registered clients (Codex, ChatGPT connectors, the Claude app) get a label
    # once their real client id has been seen; until then they are "other".
    return "other"
