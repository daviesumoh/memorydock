"""A small TTL cache with LRU eviction. Full is never a reason to clear everything."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TtlLru(Generic[K, V]):  # noqa: UP046 - one generic class; PEP 695 syntax reads worse here
    def __init__(
        self, *, ttl_seconds: float, max_entries: int, clock: Callable[[], float] = time.monotonic
    ):
        self.ttl = ttl_seconds
        self.max = max_entries
        self.clock = clock
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        hit = self._data.get(key)
        if hit is None:
            return None
        expires, value = hit
        if self.clock() >= expires:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def put(self, key: K, value: V) -> None:
        self._data[key] = (self.clock() + self.ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max:
            self._data.popitem(last=False)

    def invalidate(self, key: K) -> None:
        self._data.pop(key, None)

    def __len__(self) -> int:
        return len(self._data)
