from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any


class AsyncTTLCache:
    """Bounded process-local TTL cache with per-key single-flight loading."""

    def __init__(self, enabled: bool = True, ttl_seconds: float = 60.0, max_entries: int = 500) -> None:
        if ttl_seconds < 0 or max_entries < 1:
            raise ValueError("Cache values must be non-negative and max_entries must be positive.")
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._overflow_lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.monotonic():
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return value

    async def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        self._entries[key] = (time.monotonic() + self.ttl_seconds, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    async def get_or_set(self, key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        if not self.enabled:
            return await loader()
        cached = await self.get(key)
        if cached is not None:
            return cached
        if key not in self._locks and len(self._locks) >= self.max_entries:
            lock = self._overflow_lock
        else:
            lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = await self.get(key)
            if cached is not None:
                return cached
            value = await loader()
            await self.set(key, value)
            return value

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()