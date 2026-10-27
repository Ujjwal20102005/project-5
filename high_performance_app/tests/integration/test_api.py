import asyncio
import json

from hpapp.api.server import ApiServer
from hpapp.app import Application
from hpapp.config import Settings


async def http(port, method, path, body=None, raw=None):
    r, w = await asyncio.open_connection("127.0.0.1", port)
    if raw is not None:
        w.write(raw)
    else:
        data = b"" if body is None else json.dumps(body).encode()
        w.write(f"{method} {path} HTTP/1.1\r\nHost: x\r\nContent-Length: {len(data)}\r\n\r\n".encode() + data)
    await w.drain()
    resp = await r.read()
    w.close()
    head, _, payload = resp.partition(b"\r\n\r\n")
    return int(head.split()[1]), payload.decode()


def make_app(tmp_path, **kw):
    return Application(Settings(db_path=str(tmp_path / "api.db"), **kw))


def test_end_to_end(tmp_path):
    async def go():
        app = make_app(tmp_path)
        srv = ApiServer(app, port=0)
        port = await srv.start()
        try:
            assert (await http(port, "GET", "/health")) == (200, '{"status": "ok"}')
            recs = {"records": [{"id": f"x{i}", "payload": {"i": i}} for i in range(25)]}
            st, body = await http(port, "POST", "/process", recs)
            out = json.loads(body)
            assert st == 200 and out["succeeded"] == 25 and len(out["results"]) == 25
            st, body = await http(port, "POST", "/process", recs)       # repeat -> cached
            assert json.loads(body)["cached"] == 25
            st, body = await http(port, "POST", "/process", {"id": "solo", "payload": {}})
            assert st == 200 and json.loads(body)["total"] == 1
            st, body = await http(port, "GET", "/stats")
            s = json.loads(body)
            assert st == 200 and s["db"]["rows"] == 26 and s["cache"]["hits"] >= 25
            st, text = await http(port, "GET", "/metrics")
            assert st == 200 and "hpapp_records_processed_total" in text
            assert "hpapp_http_requests_total" in text
        finally:
            await srv.stop(); app.close()
    asyncio.run(go())


def test_error_paths(tmp_path):
    async def go():
        app = make_app(tmp_path)
        srv = ApiServer(app, port=0)
        port = await srv.start()
        try:
            assert (await http(port, "GET", "/nope"))[0] == 404
            assert (await http(port, "GET", "/process"))[0] == 405
            assert (await http(port, "POST", "/health"))[0] == 405
            assert (await http(port, "POST", "/process", {"records": []}))[0] == 400
            assert (await http(port, "POST", "/process", {"records": [{"nope": 1}]}))[0] == 400
            assert (await http(port, None, None, raw=b"garbage\r\n\r\n"))[0] == 400
            big = b"POST /process HTTP/1.1\r\nContent-Length: 99999999\r\n\r\n"
            assert (await http(port, None, None, raw=big))[0] == 413
            bad_json = b"POST /process HTTP/1.1\r\nContent-Length: 3\r\n\r\n{{{"
            assert (await http(port, None, None, raw=bad_json))[0] == 400
        finally:
            await srv.stop(); app.close()
    asyncio.run(go())


def test_rate_limiting(tmp_path):
    async def go():
        app = make_app(tmp_path, rate_limit_rps=0.001, rate_limit_burst=2)
        srv = ApiServer(app, port=0)
        port = await srv.start()
        try:
            codes = [(await http(port, "POST", "/process", {"id": str(i), "payload": {}}))[0]
                     for i in range(4)]
            assert codes == [200, 200, 429, 429]
            assert app.metrics.counters["rate_limited_total"] == 2
        finally:
            await srv.stop(); app.close()
    asyncio.run(go())


def test_application_with_process_pool(tmp_path):
    async def go():
        app = make_app(tmp_path, strategy="thorough", process_workers=2)
        try:
            from hpapp.models import Record
            rep = await app.pipeline.run([Record(str(i), {"i": i}) for i in range(6)])
            assert rep.succeeded == 6
        finally:
            app.close()
    asyncio.run(go())
