"""In-process metrics registry for per-stage latency observability.

Lightweight and dependency-free: records rolling samples per pipeline stage
(retrieval / generation / verification / total) and exposes count / avg / p95 /
last. Surfaced via ``GET /v1/metrics``. For multi-instance production this would
be replaced by Prometheus/OpenTelemetry (see FUTURE_WORK), but it gives real
timing telemetry with zero infra here.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class MetricsRegistry:
    def __init__(self, window: int = 500) -> None:
        self._window = window
        self._samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._counts: dict[str, int] = defaultdict(int)
        self._errors: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._start = time.time()

    def record(self, stage: str, ms: float) -> None:
        with self._lock:
            self._samples[stage].append(ms)
            self._counts[stage] += 1

    def incr_error(self, stage: str) -> None:
        with self._lock:
            self._errors[stage] += 1

    @staticmethod
    def _p95(values: list[float]) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = min(len(s) - 1, int(round(0.95 * (len(s) - 1))))
        return s[idx]

    def snapshot(self) -> dict:
        with self._lock:
            stages = {}
            for stage, samples in self._samples.items():
                vals = list(samples)
                stages[stage] = {
                    "count": self._counts[stage],
                    "errors": self._errors.get(stage, 0),
                    "avg_ms": round(sum(vals) / len(vals), 2) if vals else 0.0,
                    "p95_ms": round(self._p95(vals), 2),
                    "last_ms": round(vals[-1], 2) if vals else 0.0,
                }
            return {
                "uptime_seconds": round(time.time() - self._start, 1),
                "stages": stages,
            }


metrics = MetricsRegistry()


class timed:
    """Context manager: record elapsed ms into ``stage`` on exit."""

    def __init__(self, stage: str) -> None:
        self.stage = stage

    def __enter__(self) -> "timed":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        metrics.record(self.stage, (time.perf_counter() - self._t0) * 1000)
        if exc_type is not None:
            metrics.incr_error(self.stage)
