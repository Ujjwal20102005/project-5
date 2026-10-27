"""Core async pipeline: bounded queue -> N workers -> cache -> strategy -> batched DB writes."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Iterable, List, Optional, Tuple

from ..cache.ttl_cache import TTLCache
from ..database.store import SQLiteStore
from ..models import PipelineReport, Record, Result
from ..patterns.observer import (BATCH_COMPLETED, RECORD_FAILED, RECORD_PROCESSED, EventBus)
from ..patterns.strategies import ProcessingStrategy
from .resilience import CircuitBreaker, CircuitOpenError

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, strategy: ProcessingStrategy, store: SQLiteStore, cache: TTLCache,
                 bus: Optional[EventBus] = None, *, workers: int = 32, queue_size: int = 512,
                 batch_size: int = 200, max_retries: int = 2, retry_backoff: float = 0.02,
                 breaker: Optional[CircuitBreaker] = None) -> None:
        self.strategy, self.store, self.cache = strategy, store, cache
        self.bus = bus or EventBus()
        self.workers, self.queue_size, self.batch_size = workers, queue_size, batch_size
        self.max_retries, self.retry_backoff = max_retries, retry_backoff
        self.breaker = breaker

    # ---- single record ----
    async def _call_strategy(self, record: Record):
        if self.breaker is None:
            return await self.strategy.process(record.payload)
        return await self.breaker.call(lambda: self.strategy.process(record.payload))

    async def process_record(self, record: Record) -> Result:
        start = time.perf_counter()
        key = record.cache_key(self.strategy.name)
        cached = self.cache.get(key)
        if cached is not None:
            return Result(record.id, "ok", self.strategy.name, cached["digest"],
                          (time.perf_counter() - start) * 1000, cached=True)
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                out = await self._call_strategy(record)
                self.cache.set(key, out)
                return Result(record.id, "ok", self.strategy.name, out["digest"],
                              (time.perf_counter() - start) * 1000)
            except CircuitOpenError as exc:      # fail fast, never retry
                last_err = exc
                break
            except Exception as exc:             # noqa: BLE001
                last_err = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff * (2 ** attempt))
        return Result(record.id, "failed", self.strategy.name,
                      duration_ms=(time.perf_counter() - start) * 1000,
                      error=f"{type(last_err).__name__}: {last_err}")

    # ---- batch / stream ----
    async def run(self, records: Iterable[Record]) -> PipelineReport:
        start = time.perf_counter()
        queue: "asyncio.Queue[Optional[Tuple[int, Record]]]" = asyncio.Queue(self.queue_size)
        done: Dict[int, Result] = {}
        buffer: List[tuple] = []

        async def flush() -> None:
            if not buffer:
                return
            batch = buffer[:]
            buffer.clear()
            try:
                await self.store.insert_many_async(batch)
                await self.bus.publish(BATCH_COMPLETED, {"rows": len(batch)})
            except Exception:                    # noqa: BLE001
                log.exception("batch write failed (%d rows)", len(batch))

        async def worker() -> None:
            while True:
                item = await queue.get()
                try:
                    if item is None:
                        return
                    idx, record = item
                    result = await self.process_record(record)
                    done[idx] = result
                    await self.bus.publish(
                        RECORD_PROCESSED if result.status == "ok" else RECORD_FAILED, result)
                    buffer.append(SQLiteStore.row_from_result(result))
                    if len(buffer) >= self.batch_size:
                        await flush()
                except Exception:                # noqa: BLE001 - a worker must never die
                    log.exception("worker error")
                finally:
                    queue.task_done()

        n_workers = max(1, self.workers)
        tasks = [asyncio.create_task(worker()) for _ in range(n_workers)]
        count = 0
        for idx, record in enumerate(records):
            await queue.put((idx, record))      # blocks when full => back-pressure
            count += 1
        for _ in tasks:
            await queue.put(None)
        await asyncio.gather(*tasks)
        await flush()

        results = [done[i] for i in sorted(done)]
        ok = sum(1 for r in results if r.status == "ok")
        return PipelineReport(
            total=count, succeeded=ok, failed=len(results) - ok,
            cached=sum(1 for r in results if r.cached),
            elapsed_s=time.perf_counter() - start, results=results)
