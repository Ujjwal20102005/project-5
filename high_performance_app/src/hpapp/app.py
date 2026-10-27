"""Composition root: wires every component together."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, Optional

from .cache.ttl_cache import TTLCache
from .config import Settings
from .database.store import SQLiteStore
from .monitoring.metrics import Metrics
from .monitoring.observers import MetricsObserver
from .patterns.factory import StrategyFactory
from .patterns.observer import EventBus
from .services.pipeline import Pipeline
from .services.resilience import CircuitBreaker, TokenBucket


class Application:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = s = settings or Settings()
        self.metrics = Metrics()
        self.bus = EventBus()
        MetricsObserver(self.bus, self.metrics)
        self.cache = TTLCache(s.cache_size, s.cache_ttl)
        self.store = SQLiteStore(s.db_path)
        self._pool: Optional[ProcessPoolExecutor] = None
        kwargs: Dict[str, Any] = {}
        if s.strategy == "thorough" and s.process_workers > 0:
            self._pool = ProcessPoolExecutor(max_workers=s.process_workers)
            kwargs["executor"] = self._pool
        self.strategy = StrategyFactory.create(s.strategy, **kwargs)
        self.pipeline = Pipeline(
            self.strategy, self.store, self.cache, self.bus,
            workers=s.workers, queue_size=s.queue_size, batch_size=s.batch_size,
            max_retries=s.max_retries,
            breaker=CircuitBreaker(s.breaker_threshold, s.breaker_recovery))
        self.limiter_factory = lambda: TokenBucket(s.rate_limit_rps, s.rate_limit_burst)
        self.metrics.register_collector(self._cache_gauges)

    def _cache_gauges(self) -> Dict[str, float]:
        st = self.cache.stats()
        return {f"cache_{k}": v for k, v in st.items()}

    async def stats(self) -> Dict[str, Any]:
        return {
            "version": __import__("hpapp").__version__,
            "strategy": self.strategy.name,
            "cache": self.cache.stats(),
            "db": {"rows": sum((await self.store.count_by_status_async()).values()),
                   "by_status": await self.store.count_by_status_async()},
            "latency_ms": {"p50": self.metrics.percentile("record_latency_ms", 50),
                           "p95": self.metrics.percentile("record_latency_ms", 95),
                           "p99": self.metrics.percentile("record_latency_ms", 99)},
        }

    def close(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=True)
        self.store.close()
