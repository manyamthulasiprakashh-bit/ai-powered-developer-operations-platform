from __future__ import annotations

from threading import Lock
from time import perf_counter


class MetricsRegistry:
    """Small process-local metrics registry; labels are fixed by the caller."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._durations: dict[str, tuple[int, float]] = {}
        self._lock = Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def observe_duration(self, name: str, duration_seconds: float) -> None:
        with self._lock:
            count, total = self._durations.get(name, (0, 0.0))
            self._durations[name] = (count + 1, total + duration_seconds)

    def snapshot(self) -> dict[str, dict[str, int | float]]:
        with self._lock:
            snapshot: dict[str, dict[str, int | float]] = {
                name: {"value": value} for name, value in self._counters.items()
            }
            for name, (count, total) in self._durations.items():
                snapshot[name] = {"count": count, "total_seconds": round(total, 6)}
            return snapshot

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._durations.clear()


metrics = MetricsRegistry()


def timed(metric_name: str):
    def decorator(function):
        async def wrapped(*args, **kwargs):
            started = perf_counter()
            try:
                return await function(*args, **kwargs)
            finally:
                metrics.observe_duration(metric_name, perf_counter() - started)

        return wrapped

    return decorator