"""MCP tools: one module per area, each exposing register(mcp)."""

from __future__ import annotations

import importlib
import pkgutil

from fastmcp import FastMCP


def register_all(mcp: FastMCP) -> None:
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{__name__}.{info.name}")
        module.register(mcp)
