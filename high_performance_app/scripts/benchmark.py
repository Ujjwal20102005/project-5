#!/usr/bin/env python3
"""Reproducible before/after benchmarks. Writes performance/benchmark_results.{json,md}.

Usage:  PYTHONPATH=src python scripts/benchmark.py
"""
import asyncio
import json
import os
import platform
import random
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

from hpapp.cache.ttl_cache import TTLCache
from hpapp.database.store import SQLiteStore
from hpapp.models import Record
from hpapp.patterns.strategies import IOBoundStrategy, ThoroughProcessingStrategy
from hpapp.services.pipeline import Pipeline

OUT = os.path.join(os.path.dirname(__file__), "..", "performance")
CORES = os.cpu_count() or 1


def recs(n, prefix="r"):
    return [Record(f"{prefix}{i}", {"n": i}) for i in range(n)]


def run(pipe, records):
    t0 = time.perf_counter()
    rep = asyncio.run(pipe.run(records))
    return time.perf_counter() - t0, rep


def pct(before, after):
    return round((before - after) / before * 100, 1)


def main():
    tmp = tempfile.mkdtemp()
    results = {"environment": {"python": platform.python_version(), "cpu_cores": CORES,
                               "platform": platform.platform()}}

    # 1. asyncio concurrency on I/O-bound work -------------------------------------------
    n, lat = 300, 0.02
    store = SQLiteStore(f"{tmp}/a.db")
    seq, _ = run(Pipeline(IOBoundStrategy(lat), store, TTLCache(), workers=1), recs(n, "s"))
    con, _ = run(Pipeline(IOBoundStrategy(lat), store, TTLCache(), workers=100), recs(n, "c"))
    results["io_concurrency"] = {
        "records": n, "simulated_latency_ms": lat * 1000,
        "sequential_s": round(seq, 3), "concurrent_s": round(con, 3),
        "sequential_rps": round(n / seq, 1), "concurrent_rps": round(n / con, 1),
        "speedup_x": round(seq / con, 1)}

    # 2. process pool vs thread pool on CPU-bound work -----------------------------------
    n, rounds = 96, 30_000
    store2 = SQLiteStore(f"{tmp}/b.db")
    thr, _ = run(Pipeline(ThoroughProcessingStrategy(None, rounds), store2, TTLCache(), workers=16),
                 recs(n, "t"))
    with ProcessPoolExecutor(max_workers=CORES) as pool:
        run(Pipeline(ThoroughProcessingStrategy(pool, 10), store2, TTLCache()), recs(CORES, "w"))  # warm-up
        prc, _ = run(Pipeline(ThoroughProcessingStrategy(pool, rounds), store2, TTLCache(), workers=16),
                     recs(n, "p"))
    results["cpu_parallelism"] = {
        "records": n, "hash_rounds": rounds, "workers": CORES,
        "thread_pool_s": round(thr, 3), "process_pool_s": round(prc, 3),
        "speedup_x": round(thr / prc, 2)}

    # 3. cache effectiveness ---------------------------------------------------------------
    n = 400
    cache = TTLCache(10_000, 600)
    p = Pipeline(ThoroughProcessingStrategy(None, 20_000), SQLiteStore(f"{tmp}/c.db"), cache, workers=8)
    cold, _ = run(p, recs(n, "k"))
    warm, rep = run(p, recs(n, "k"))
    results["cache"] = {"records": n, "cold_s": round(cold, 3), "warm_s": round(warm, 3),
                        "speedup_x": round(cold / warm, 1), "hit_rate": cache.stats()["hit_rate"],
                        "cached_in_warm_run": rep.cached}

    # 4. batched vs row-by-row writes --------------------------------------------------------
    n = 3000
    rows = [(f"i{i}", "ok", "fast", "d", 1.0, time.time()) for i in range(n)]
    s1 = SQLiteStore(f"{tmp}/d1.db")
    t0 = time.perf_counter()
    for r in rows:
        s1.insert_many([r])
    single = time.perf_counter() - t0
    s2 = SQLiteStore(f"{tmp}/d2.db")
    t0 = time.perf_counter()
    s2.insert_many(rows)
    batch = time.perf_counter() - t0
    results["db_writes"] = {"rows": n, "row_by_row_s": round(single, 3), "batched_s": round(batch, 4),
                            "speedup_x": round(single / batch, 1),
                            "batched_rows_per_s": round(n / batch)}

    # 5. index effect on the hot query ---------------------------------------------------------
    n = 300_000
    random.seed(1)
    now = time.time()
    data = [(f"r{i}", "failed" if random.random() < 0.01 else "ok", "fast", "d", 1.0, now + i)
            for i in range(n)]
    timings = {}
    for label, idx in (("no_index", False), ("indexed", True)):
        st = SQLiteStore(f"{tmp}/e_{label}.db", with_indexes=idx)
        st.insert_many(data)
        t0 = time.perf_counter()
        for _ in range(50):
            st.recent_by_status("failed", 20)
        timings[label] = (time.perf_counter() - t0) / 50 * 1000
        timings[label + "_plan"] = st.explain_recent_by_status()
    results["db_index"] = {
        "rows": n, "no_index_ms_per_query": round(timings["no_index"], 3),
        "indexed_ms_per_query": round(timings["indexed"], 3),
        "speedup_x": round(timings["no_index"] / timings["indexed"], 1),
        "plan_no_index": timings["no_index_plan"], "plan_indexed": timings["indexed_plan"]}

    # 6. end-to-end peak pipeline throughput -----------------------------------------------------
    from hpapp.patterns.strategies import FastProcessingStrategy
    n = 20_000
    st = SQLiteStore(f"{tmp}/f.db")
    pl = Pipeline(FastProcessingStrategy(), st, TTLCache(50_000), workers=32, batch_size=500)
    el, rep = run(pl, recs(n, "e"))
    lat = sorted(r.duration_ms for r in rep.results)
    results["end_to_end_fast"] = {
        "records": n, "elapsed_s": round(el, 3), "throughput_rps": round(n / el),
        "latency_ms": {"p50": round(lat[n // 2], 3), "p95": round(lat[int(n * .95)], 3),
                       "p99": round(lat[int(n * .99)], 3)}}

    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    with open(f"{OUT}/benchmark_results.md", "w") as f:
        f.write(render_md(results))
    print(render_md(results))


def render_md(r):
    e, io, cpu, c, w, ix, ee = (r["environment"], r["io_concurrency"], r["cpu_parallelism"],
                                r["cache"], r["db_writes"], r["db_index"], r["end_to_end_fast"])
    note = ("\n> **Note:** this run had a single CPU core, so the process-pool row cannot show a gain "
            "(processes only help when >1 core is available). Re-run on a multi-core machine; "
            "expect close to N-core scaling for CPU-bound work.\n") if e["cpu_cores"] == 1 else ""
    return f"""# Benchmark Results

Environment: Python {e['python']}, {e['cpu_cores']} CPU cores, {e['platform']}
Generated by `scripts/benchmark.py` (numbers vary by machine; relative gains are what matter).

| Optimization | Before | After | Improvement |
|---|---|---|---|
| asyncio concurrency ({io['records']} I/O calls @ {io['simulated_latency_ms']:.0f} ms) | {io['sequential_s']} s ({io['sequential_rps']} rps) | {io['concurrent_s']} s ({io['concurrent_rps']} rps) | **{io['speedup_x']}x** |
| Process pool vs thread pool ({cpu['records']} CPU-bound records, {cpu['workers']} cores) | {cpu['thread_pool_s']} s | {cpu['process_pool_s']} s | **{cpu['speedup_x']}x** |
| LRU/TTL cache (cold vs warm, hit rate {c['hit_rate']:.0%} overall) | {c['cold_s']} s | {c['warm_s']} s | **{c['speedup_x']}x** |
| Batched DB writes ({w['rows']} rows) | {w['row_by_row_s']} s | {w['batched_s']} s | **{w['speedup_x']}x** |
| Composite index on hot query ({ix['rows']:,} rows) | {ix['no_index_ms_per_query']} ms | {ix['indexed_ms_per_query']} ms | **{ix['speedup_x']}x** |

{note}
## Query plans
- Without index: `{'; '.join(ix['plan_no_index'])}`
- With index: `{'; '.join(ix['plan_indexed'])}`

## End-to-end peak (fast strategy, {ee['records']:,} records, 32 workers, batch 500)
- Throughput: **{ee['throughput_rps']:,} records/s** ({ee['elapsed_s']} s total)
- Per-record processing latency (excludes queue wait): p50 {ee['latency_ms']['p50']} ms, p95 {ee['latency_ms']['p95']} ms, p99 {ee['latency_ms']['p99']} ms
"""


if __name__ == "__main__":
    main()
