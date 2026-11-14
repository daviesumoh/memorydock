"""Collect `router` from every module in a package, so adding a route file needs no shared list."""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from fastapi import APIRouter


def collect(package: ModuleType) -> list[APIRouter]:
    routers = []
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            routers.append(router)
    return routers
