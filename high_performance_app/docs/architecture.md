# Architecture Design

Data Processing Pipeline exposed over HTTP. See `architecture/architecture.mmd` for the diagram
(render at https://mermaid.live or in GitHub) and `architecture/design_decisions.md` for rationale.

## Layers (clear separation of concerns)
| Layer | Package | Responsibility |
|---|---|---|
| API | `hpapp.api` | HTTP parsing, routing, rate limiting, error mapping. No business logic. |
| Service | `hpapp.services` | `Pipeline` orchestration, retry, circuit breaker, rate limiter |
| Domain patterns | `hpapp.patterns` | Strategies, factory, event bus |
| Infrastructure | `hpapp.cache`, `hpapp.database` | TTL-LRU cache, pooled SQLite store |
| Observability | `hpapp.monitoring`, `hpapp.utils` | Metrics, JSON logging, profiling |
| Wiring | `hpapp.app`, `hpapp.config` | Dependency injection, env config |

## Request flow
1. `POST /process` -> token-bucket check per client IP (429 if exceeded).
2. Records enter a **bounded asyncio queue**; `N` worker tasks pull from it.
3. Each worker checks the **cache**; on miss it calls the **strategy** through the **circuit breaker**, with retries.
4. Results go to a **write buffer**, flushed in **batches** to SQLite (in a thread, off the event loop).
5. Every result publishes an **event**; `MetricsObserver` updates counters and latency histograms.
6. `GET /metrics` exposes Prometheus text; `GET /stats` exposes a JSON summary.

## Data structures & algorithms
- `OrderedDict` for O(1) LRU get/set/evict; TTL checked lazily on read.
- Token bucket (O(1) refill math, no timers).
- Fixed-bucket histogram (bisect, O(log b)) plus a 10k-sample reservoir for percentiles.
- 3-state circuit breaker (closed -> open -> half-open).
- Content-addressed cache key: `sha256(strategy + canonical-JSON(payload))`, so key order never matters.

## API
| Endpoint | Description |
|---|---|
| `POST /process` | Body: `{"records":[{"id":"..","payload":{..}}]}` (1-1000) or a single record |
| `GET /health`, `GET /ready` | Liveness / readiness |
| `GET /stats` | Cache, DB, latency percentiles |
| `GET /metrics` | Prometheus exposition |
