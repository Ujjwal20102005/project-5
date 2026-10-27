import json
import logging

from hpapp.config import Settings
from hpapp.models import PipelineReport, Record, Result
from hpapp.monitoring.logging_config import JsonFormatter, configure_logging
from hpapp.monitoring.metrics import Metrics
from hpapp.utils.profiling import Timer, profile


def test_metrics_counters_gauges_percentiles():
    m = Metrics()
    m.inc("a"); m.inc("a", 2)
    m.set_gauge("g", 5)
    for v in range(1, 101):
        m.observe("lat", v)
    assert m.counters["a"] == 3
    assert m.percentile("lat", 50) in (50, 51)
    assert m.percentile("lat", 99) >= 99
    assert m.percentile("empty", 50) == 0.0


def test_prometheus_rendering_and_collectors():
    m = Metrics()
    m.inc("req_total"); m.observe("lat", 3); m.observe("lat", 9999)
    m.register_collector(lambda: {"cache_size": 7})
    text = m.render_prometheus()
    assert "hpapp_req_total 1.0" in text
    assert 'hpapp_lat_bucket{le="5"} 1' in text
    assert 'hpapp_lat_bucket{le="+Inf"} 2' in text
    assert "hpapp_cache_size 7" in text


def test_settings_from_env():
    s = Settings.from_env({"HPAPP_PORT": "9000", "HPAPP_CACHE_TTL": "1.5",
                           "HPAPP_STRATEGY": "io"})
    assert (s.port, s.cache_ttl, s.strategy) == (9000, 1.5, "io")
    assert Settings.from_env({}).port == 8080


def test_models():
    r = Record("1", {"b": 1, "a": 2})
    assert r.canonical() == '{"a":2,"b":1}'
    assert r.cache_key("fast") != r.cache_key("io")
    res = Result("1", "ok", "fast", "d", 1.23456)
    rep = PipelineReport(2, 2, 0, 0, 0.5, [res])
    assert rep.throughput == 4 and rep.to_dict()["results"][0]["duration_ms"] == 1.235
    assert "results" not in rep.to_dict(include_results=False)
    assert PipelineReport(0, 0, 0, 0, 0.0, []).throughput == 0.0


def test_json_logging():
    rec = logging.LogRecord("n", logging.ERROR, "f", 1, "hello %s", ("x",), None)
    assert json.loads(JsonFormatter().format(rec))["msg"] == "hello x"
    try:
        raise ValueError("e")
    except ValueError:
        import sys
        rec2 = logging.LogRecord("n", logging.ERROR, "f", 1, "m", (), sys.exc_info())
    assert "ValueError" in json.loads(JsonFormatter().format(rec2))["exc"]
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_profiling_helpers():
    with Timer() as t:
        sum(range(1000))
    assert t.elapsed >= 0
    with profile(top=3) as p:
        sum(range(1000))
    assert "function calls" in p.report
