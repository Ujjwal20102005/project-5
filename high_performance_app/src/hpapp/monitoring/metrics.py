"""Dependency-free metrics registry with Prometheus text exposition."""
from __future__ import annotations

import bisect
import threading
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List

DEFAULT_BUCKETS_MS = (1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500)


class Metrics:
    def __init__(self, buckets=DEFAULT_BUCKETS_MS, reservoir: int = 10_000) -> None:
        self._lock = threading.Lock()
        self.buckets = tuple(buckets)
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = {}
        self._hist: Dict[str, List[int]] = {}
        self._hist_sum: Dict[str, float] = defaultdict(float)
        self._hist_count: Dict[str, int] = defaultdict(int)
        self._samples: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=reservoir))
        self._collectors: List[Callable[[], Dict[str, float]]] = []

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self.counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self.gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            counts = self._hist.setdefault(name, [0] * (len(self.buckets) + 1))
            counts[bisect.bisect_left(self.buckets, value)] += 1
            self._hist_sum[name] += value
            self._hist_count[name] += 1
            self._samples[name].append(value)

    def percentile(self, name: str, q: float) -> float:
        with self._lock:
            data = sorted(self._samples.get(name, ()))
        if not data:
            return 0.0
        k = min(len(data) - 1, max(0, int(round(q / 100 * (len(data) - 1)))))
        return data[k]

    def register_collector(self, fn: Callable[[], Dict[str, float]]) -> None:
        """Collectors return gauges computed at scrape time (e.g. cache stats)."""
        self._collectors.append(fn)

    def snapshot(self) -> Dict[str, object]:
        gauges = dict(self.gauges)
        for fn in self._collectors:
            gauges.update(fn())
        return {"counters": dict(self.counters), "gauges": gauges}

    def render_prometheus(self, prefix: str = "hpapp_") -> str:
        snap = self.snapshot()
        lines: List[str] = []
        for name, v in sorted(snap["counters"].items()):
            lines += [f"# TYPE {prefix}{name} counter", f"{prefix}{name} {v}"]
        for name, v in sorted(snap["gauges"].items()):
            lines += [f"# TYPE {prefix}{name} gauge", f"{prefix}{name} {v}"]
        with self._lock:
            for name, counts in sorted(self._hist.items()):
                lines.append(f"# TYPE {prefix}{name} histogram")
                cum = 0
                for le, c in zip(self.buckets, counts):
                    cum += c
                    lines.append(f'{prefix}{name}_bucket{{le="{le}"}} {cum}')
                lines.append(f'{prefix}{name}_bucket{{le="+Inf"}} {self._hist_count[name]}')
                lines.append(f"{prefix}{name}_sum {self._hist_sum[name]}")
                lines.append(f"{prefix}{name}_count {self._hist_count[name]}")
        return "\n".join(lines) + "\n"
