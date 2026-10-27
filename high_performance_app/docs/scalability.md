# Scalability Considerations

- **Vertical:** raise `HPAPP_WORKERS`; set `HPAPP_PROCESS_WORKERS` = cores for CPU-bound strategies.
- **Horizontal:** stateless API pods behind a Service; HPA scales on CPU.
- **Known limits (be honest about them):**
  - SQLite is a single-writer file DB and the Kubernetes manifest uses a per-pod `emptyDir`. For real
    multi-replica production, swap `SQLiteStore` for PostgreSQL (same interface: `insert_many`, `get`, `count_by_status`...)
    with read replicas, or add a shared message queue (RabbitMQ/Kafka) in front.
  - The cache is per-process; use Redis for cross-pod hit rate.
  - Rate limiting is per-pod; use an edge/API gateway limiter for global limits.
- **Trade-offs:** larger batches = higher throughput but more data at risk on crash; larger caches = fewer
  recomputations but more memory; more workers = better I/O overlap but diminishing returns and more contention.
