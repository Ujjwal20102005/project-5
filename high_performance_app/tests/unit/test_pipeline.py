import asyncio

from conftest import make_records
from hpapp.models import Record
from hpapp.monitoring.metrics import Metrics
from hpapp.monitoring.observers import MetricsObserver
from hpapp.patterns.observer import EventBus
from hpapp.patterns.strategies import FastProcessingStrategy, ProcessingStrategy
from hpapp.services.pipeline import Pipeline
from hpapp.services.resilience import CircuitBreaker


class Flaky(ProcessingStrategy):
    name = "flaky"
    def __init__(self, fail_times): self.calls, self.fail_times = 0, fail_times
    async def process(self, data):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient")
        return {"digest": "ok"}


def test_run_persists_and_preserves_order(store, cache):
    p = Pipeline(FastProcessingStrategy(), store, cache, workers=8, batch_size=7)
    recs = make_records(50)
    rep = asyncio.run(p.run(recs))
    assert [r.id for r in rep.results] == [r.id for r in recs]
    assert (rep.total, rep.succeeded, rep.failed) == (50, 50, 0)
    assert store.count() == 50 and rep.throughput > 0


def test_cache_hits_on_repeat(store, cache):
    p = Pipeline(FastProcessingStrategy(), store, cache)
    asyncio.run(p.run(make_records(20)))
    rep = asyncio.run(p.run(make_records(20)))
    assert rep.cached == 20 and cache.stats()["hit_rate"] == 0.5


def test_retry_then_success(store, cache):
    p = Pipeline(Flaky(2), store, cache, max_retries=2, retry_backoff=0)
    rep = asyncio.run(p.run([Record("a", {"x": 1})]))
    assert rep.succeeded == 1


def test_retries_exhausted_marks_failed(store, cache):
    p = Pipeline(Flaky(99), store, cache, max_retries=1, retry_backoff=0)
    rep = asyncio.run(p.run([Record("a", {})]))
    assert rep.failed == 1 and "RuntimeError" in rep.results[0].error
    assert store.count_by_status() == {"failed": 1}


def test_breaker_fails_fast(store, cache):
    strat = Flaky(10_000)
    p = Pipeline(strat, store, cache, workers=1, max_retries=0,
                 breaker=CircuitBreaker(2, 1000))
    rep = asyncio.run(p.run([Record(str(i), {"i": i}) for i in range(10)]))
    assert rep.failed == 10
    assert strat.calls == 2                       # remaining 8 short-circuited
    assert "CircuitOpenError" in rep.results[-1].error


def test_events_feed_metrics(store, cache):
    bus, m = EventBus(), Metrics()
    MetricsObserver(bus, m)
    p = Pipeline(Flaky(99), store, cache, bus, max_retries=0, batch_size=2)
    asyncio.run(p.run([Record("a", {}), Record("b", {"z": 1}), Record("c", {"q": 1})]))
    assert m.counters["records_failed_total"] == 3
    assert m.counters["db_rows_written_total"] == 3 and m.counters["db_batches_total"] == 2
    p2 = Pipeline(FastProcessingStrategy(), store, cache, bus)
    asyncio.run(p2.run(make_records(2))); asyncio.run(p2.run(make_records(2)))
    assert m.counters["records_processed_total"] == 4
    assert m.counters["records_cached_total"] == 2


def test_db_failure_does_not_crash_pipeline(store, cache):
    async def bad(rows): raise RuntimeError("disk full")
    store.insert_many_async = bad
    p = Pipeline(FastProcessingStrategy(), store, cache, batch_size=2)
    rep = asyncio.run(p.run(make_records(5)))
    assert rep.succeeded == 5


def test_backpressure_with_tiny_queue(store, cache):
    p = Pipeline(FastProcessingStrategy(), store, cache, workers=2, queue_size=1)
    rep = asyncio.run(p.run(iter(make_records(100))))   # generator input
    assert rep.total == 100
