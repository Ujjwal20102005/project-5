# Architecture Decision Records

| # | Decision | Why | Trade-off |
|---|----------|-----|-----------|
| 1 | **asyncio** for the request/pipeline layer | Thousands of concurrent in-flight I/O waits on one thread; no lock contention | CPU-bound work blocks the loop unless offloaded |
| 2 | **ProcessPool** for CPU-bound strategy | Escapes the GIL; scales with cores | Pickling overhead; no benefit on 1 core |
| 3 | **Bounded queue + N workers** | Back-pressure: memory stays flat under overload | Producers wait when full |
| 4 | **Batched DB writes** (one transaction per N rows) | ~15x faster than commit-per-row (measured) | Up to N rows lost on hard crash before flush |
| 5 | **SQLite WAL + connection pool** | Zero-ops, concurrent readers during writes | Single-writer; use PostgreSQL for multi-replica (see docs/scalability.md) |
| 6 | **Composite index (status, created_at)** | Hot query went from full scan to index search (~200x, measured) | Slightly slower writes, extra disk |
| 7 | **TTL-LRU cache keyed by SHA-256(strategy+payload)** | Idempotent work is never repeated | Per-process cache; use Redis for cross-replica sharing |
| 8 | **Circuit breaker + retry w/ exponential backoff** | Fail fast when a dependency is down; recover automatically | Some requests rejected while open |
| 9 | **Stdlib-only runtime** | Tiny attack surface, fast cold start, reproducible | Hand-rolled HTTP server is minimal (swap in FastAPI/aiohttp if needed) |
| 10 | **Observer / EventBus for metrics** | Pipeline has no knowledge of monitoring; easy to add audit logs, webhooks | Slight per-event overhead |

## Design patterns used
- **Strategy** - `patterns/strategies.py` (fast / io / thorough, swappable at runtime)
- **Factory** - `patterns/factory.py` (`StrategyFactory.create/register`)
- **Observer** - `patterns/observer.py` (`EventBus`) + `monitoring/observers.py`
- **Circuit Breaker, Token Bucket** - `services/resilience.py`
- **Composition Root / Dependency Injection** - `app.py`
- **Object Pool** - `database/store.py::ConnectionPool`
