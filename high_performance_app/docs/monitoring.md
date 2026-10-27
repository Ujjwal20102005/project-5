# Monitoring & Observability

**Metrics** (`GET /metrics`, Prometheus format): `records_processed_total`, `records_failed_total`,
`records_cached_total`, `record_latency_ms` (histogram), `http_requests_total`,
`http_responses_<code>_total`, `http_latency_ms`, `rate_limited_total`, `db_batches_total`,
`db_rows_written_total`, `cache_hit_rate/size/evictions/...`.

**Most important signals:** p95/p99 latency (not averages), error rate, cache hit rate,
queue/worker saturation (watch latency growth), rate-limited count, DB batch write rate.

**Alerts** (`monitoring/alerts.yml`): error rate > 1%, p95 > 250 ms, cache hit rate < 50%, sustained rate limiting.
**Dashboard:** `monitoring/grafana/dashboard.json`.
**Logs:** structured JSON to stdout (`monitoring/logging_config.py`) - ship with any collector (ELK/Loki).
