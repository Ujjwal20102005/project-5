# Visual documentation

Captured from real runs in this repository:
- `test_output.txt` - full pytest + coverage output
- `live_demo_output.txt` - running server: `/health`, `/process`, load test, `/stats`, `/metrics`
- `../../performance/benchmark_results.md` - benchmark table
- `../../performance/coverage_html/index.html` - open in a browser for the coverage report

For graphical screenshots (Grafana dashboard etc.), run `docker compose -f docker/docker-compose.yml up`,
open http://localhost:3000, import `monitoring/grafana/dashboard.json`, run `scripts/load_test.py`, and screenshot.
