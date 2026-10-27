# hpapp - High-Performance Data Processing Pipeline

**Month 5 project - Specialization: Data Processing Pipeline (Option 2).**
An asynchronous, cache-accelerated, observable record-processing service with parallel CPU offloading,
batched indexed persistence, resilience patterns, Prometheus metrics, and production deployment config.
Runtime has **zero third-party dependencies** (pure Python 3.10+ stdlib).

## Performance highlights (measured; see `performance/benchmark_results.md`)
| Optimization | Before -> After |
|---|---|
| asyncio concurrency, 300 I/O calls @ 20 ms | 6.1 s -> 0.07 s (**~90x**) |
| Result cache (warm vs cold) | 3.2 s -> 0.007 s (**~500x**) |
| Batched DB writes (3,000 rows) | 154 ms -> 10.6 ms (**~15x**) |
| Composite index on hot query (300k rows) | 15 ms -> 0.08 ms (**~200x**) |
| End-to-end peak, fast strategy | **~70,000 records/s** in-process; ~1,000 HTTP req/s (10 records each) on a 1-core sandbox |

Honest caveat: the sandbox had 1 CPU core, so the process-pool speedup could not be demonstrated
(it needs >1 core). Re-run `make bench` on your machine.

## Quick start
```bash
pip install -r requirements.txt
make test                                   # 40 tests, ~98% coverage (gate: 80%)
make bench                                  # regenerate performance/ results
make run                                    # server on :8080
curl -X POST localhost:8080/process -d '{"records":[{"id":"a","payload":{"x":1}}]}'
curl localhost:8080/metrics
```
Docker: `make up` (app + Prometheus + Grafana). Kubernetes: `scripts/deploy.sh`.

## Requirements checklist
| Requirement | Where |
|---|---|
| Specialization chosen | Data Processing Pipeline |
| Concurrent / parallel processing | `services/pipeline.py` (asyncio workers), `ThoroughProcessingStrategy` (process pool) |
| DB indexing & query optimization | `database/store.py` (composite index, WAL, pool, batching, `EXPLAIN QUERY PLAN` tests) |
| Test suite >80% coverage | `tests/` - 40 tests, ~98% (enforced by `pytest.ini`) |
| Profiling & optimization | `utils/profiling.py`, `scripts/benchmark.py`, `docs/performance_guide.md` |
| Design patterns | Strategy, Factory, Observer, Circuit Breaker, Token Bucket, DI, Object Pool |
| Modular architecture | `api / services / patterns / cache / database / monitoring` |
| Caching | `cache/ttl_cache.py` (thread-safe LRU + TTL + stats) |
| Monitoring & observability | `monitoring/` (metrics, JSON logs, alerts, Grafana dashboard) |
| Production deployment config | `docker/`, `kubernetes/`, `scripts/deploy.sh` |

## Layout
```
src/hpapp/   api/ services/ patterns/ cache/ database/ monitoring/ utils/ app.py config.py models.py main.py
tests/       unit/ integration/ performance/
docker/  kubernetes/  monitoring/  scripts/  performance/  architecture/  docs/
```

## Documentation
`docs/architecture.md` - `docs/performance_guide.md` - `docs/deployment.md` - `docs/monitoring.md` -
`docs/scalability.md` - `docs/testing.md` - `architecture/design_decisions.md` - `docs/screenshots/` (real run captures)

## Configuration
`HPAPP_PORT, HPAPP_DB_PATH, HPAPP_STRATEGY (fast|io|thorough), HPAPP_WORKERS, HPAPP_QUEUE_SIZE, HPAPP_BATCH_SIZE,
HPAPP_CACHE_SIZE, HPAPP_CACHE_TTL, HPAPP_PROCESS_WORKERS, HPAPP_RATE_LIMIT_RPS, HPAPP_RATE_LIMIT_BURST, HPAPP_LOG_LEVEL`

## Analysis questions (answers)
1. **Best gains?** Indexing, caching and concurrency each gave 1-2 orders of magnitude, but on different workloads; always profile first.
2. **Architecture vs scalability?** Stateless API + bounded queues + externalized state (DB/cache) lets you scale horizontally; per-pod SQLite/cache is the limiter.
3. **Key metrics?** p95/p99 latency, error rate, throughput, cache hit rate, saturation (queue/worker usage).
4. **Managing concurrency?** Semaphore-like worker count, bounded queue for back-pressure, offload blocking/CPU work, timeouts and circuit breakers.
5. **Trade-offs?** Batching (throughput vs durability), caching (speed vs memory/staleness), workers (overlap vs contention), indexes (read speed vs write cost).
