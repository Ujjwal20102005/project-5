# Performance Optimization Guide

Method: **measure -> change one thing -> re-measure.** All numbers below come from
`scripts/benchmark.py` (see `performance/benchmark_results.md`).

| Technique | Where | When it helps | Measured here |
|---|---|---|---|
| asyncio concurrency | `Pipeline.run` | I/O-bound work (network, DB) | ~90x on 300 x 20 ms calls |
| Process pool | `ThoroughProcessingStrategy` | CPU-bound work, multi-core | Needs >1 core (sandbox had 1) |
| Result caching | `TTLCache` | Repeated / idempotent inputs | ~500x on a warm run |
| Batched writes | `SQLiteStore.insert_many` | Many small writes | ~15x |
| Composite index | `idx_results_status_created` | Filter + sort queries | ~200x on 300k rows |
| Back-pressure | bounded queue | Overload protection | Flat memory |
| WAL + pooling | `ConnectionPool` | Concurrent readers/writers | Avoids connect cost per query |

## Choosing a concurrency model
- **I/O-bound** -> `asyncio` (this app's default; `io` strategy).
- **CPU-bound** -> `ProcessPoolExecutor` (`HPAPP_STRATEGY=thorough HPAPP_PROCESS_WORKERS=<cores>`).
- **Blocking libraries** (sqlite3) -> `asyncio.to_thread` so the loop is never blocked.
- Threads don't speed up CPU-bound Python because of the GIL.

## Profiling
```python
from hpapp.utils.profiling import profile, Timer
with profile(top=15) as p:
    run_workload()
print(p.report)          # cProfile, sorted by cumulative time
```
For live systems use `/metrics` histograms (p50/p95/p99) rather than average latency.
Use `store.explain_recent_by_status()` to verify queries hit indexes.

## Tuning knobs (env vars)
`HPAPP_WORKERS` (concurrency), `HPAPP_QUEUE_SIZE`, `HPAPP_BATCH_SIZE`, `HPAPP_CACHE_SIZE`,
`HPAPP_CACHE_TTL`, `HPAPP_PROCESS_WORKERS`, `HPAPP_RATE_LIMIT_RPS/BURST`.
