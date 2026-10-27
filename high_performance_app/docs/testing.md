# Testing

```bash
python -m pytest                 # 40 tests, coverage gate >= 80% enforced in pytest.ini
python -m pytest tests/unit      # fast unit tests only
python -m pytest -m performance  # throughput regression guards
```
- `tests/unit` - cache, store (incl. query-plan assertions), patterns, resilience, metrics, config, pipeline.
- `tests/integration` - real TCP server: happy path, error paths (400/404/405/413/429), rate limiting, process pool.
- `tests/performance` - concurrency >5x vs sequential, throughput floor, batch vs single insert.
- Deterministic: time-dependent code (cache TTL, breaker, token bucket) takes an injectable clock.
- HTML coverage report: `performance/coverage_html/index.html`.
