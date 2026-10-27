"""Performance regression guards. Thresholds are deliberately conservative so CI
on slow machines doesn't flake, while still catching order-of-magnitude regressions."""
import asyncio
import time

import pytest
from conftest import make_records
from hpapp.patterns.strategies import FastProcessingStrategy, IOBoundStrategy
from hpapp.services.pipeline import Pipeline

pytestmark = pytest.mark.performance


def test_concurrency_beats_sequential_for_io(store, cache):
    n, latency = 100, 0.02
    p = Pipeline(IOBoundStrategy(latency), store, cache, workers=50)
    t0 = time.perf_counter()
    rep = asyncio.run(p.run(make_records(n)))
    elapsed = time.perf_counter() - t0
    assert rep.succeeded == n
    assert elapsed < (n * latency) / 5            # >5x faster than sequential (2.0s)


def test_fast_strategy_throughput(store, cache):
    p = Pipeline(FastProcessingStrategy(), store, cache, workers=16, batch_size=500)
    rep = asyncio.run(p.run(make_records(5000)))
    assert rep.throughput > 1000                  # records / second


def test_batch_insert_faster_than_row_by_row(store):
    import time as t
    rows = [(f"a{i}", "ok", "fast", "d", 1.0, t.time()) for i in range(500)]
    t0 = t.perf_counter(); store.insert_many(rows); batch = t.perf_counter() - t0
    t0 = t.perf_counter()
    for i in range(500):
        store.insert_many([(f"b{i}", "ok", "fast", "d", 1.0, t.time())])
    single = t.perf_counter() - t0
    assert batch < single
