"""Minimal asyncio HTTP/1.1 server (stdlib only) exposing the pipeline."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, Tuple

from ..app import Application
from ..models import Record
from ..services.resilience import TokenBucket

log = logging.getLogger(__name__)

MAX_BODY = 1_000_000
MAX_RECORDS = 1000
REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
           413: "Payload Too Large", 429: "Too Many Requests", 500: "Internal Server Error"}

Response = Tuple[int, str, bytes]


def _json(status: int, obj) -> Response:
    return status, "application/json", json.dumps(obj).encode()


class ApiServer:
    def __init__(self, app: Application, host: str = "127.0.0.1", port: int = 8080,
                 read_timeout: float = 5.0) -> None:
        self.app, self.host, self.port, self.read_timeout = app, host, port, read_timeout
        self._buckets: Dict[str, TokenBucket] = {}
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # ---- connection handling ----
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        start = time.perf_counter()
        peer = writer.get_extra_info("peername")
        ip = peer[0] if peer else "unknown"
        try:
            status, ctype, body = await self._read_and_route(reader, ip)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError):
            status, ctype, body = _json(400, {"error": "bad request"})
        except Exception:                            # noqa: BLE001
            log.exception("unhandled error")
            status, ctype, body = _json(500, {"error": "internal error"})
        m = self.app.metrics
        m.inc("http_requests_total")
        m.inc(f"http_responses_{status}_total")
        m.observe("http_latency_ms", (time.perf_counter() - start) * 1000)
        head = (f"HTTP/1.1 {status} {REASONS.get(status, 'OK')}\r\n"
                f"Content-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n").encode()
        try:
            writer.write(head + body)
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def _read_and_route(self, reader, ip: str) -> Response:
        line = await asyncio.wait_for(reader.readline(), self.read_timeout)
        parts = line.decode("latin-1").split()
        if len(parts) < 2:
            raise ValueError("malformed request line")
        method, path = parts[0], parts[1].split("?")[0]
        headers: Dict[str, str] = {}
        while True:
            h = await asyncio.wait_for(reader.readline(), self.read_timeout)
            if h in (b"\r\n", b"\n", b""):
                break
            k, _, v = h.decode("latin-1").partition(":")
            headers[k.strip().lower()] = v.strip()
        length = int(headers.get("content-length", "0") or 0)
        if length > MAX_BODY:
            return _json(413, {"error": "payload too large"})
        body = await asyncio.wait_for(reader.readexactly(length), self.read_timeout) if length else b""
        return await self._route(method, path, body, ip)

    # ---- routes ----
    async def _route(self, method: str, path: str, body: bytes, ip: str) -> Response:
        if path in ("/health", "/ready"):
            return _json(200, {"status": "ok"}) if method == "GET" else _json(405, {"error": "method"})
        if path == "/metrics":
            return 200, "text/plain; version=0.0.4", self.app.metrics.render_prometheus().encode()
        if path == "/stats":
            return _json(200, await self.app.stats())
        if path == "/process":
            if method != "POST":
                return _json(405, {"error": "use POST"})
            return await self._process(body, ip)
        return _json(404, {"error": "not found"})

    async def _process(self, body: bytes, ip: str) -> Response:
        if len(self._buckets) > 10_000:
            self._buckets.clear()
        bucket = self._buckets.setdefault(ip, self.app.limiter_factory())
        if not bucket.allow():
            self.app.metrics.inc("rate_limited_total")
            return _json(429, {"error": "rate limit exceeded"})
        try:
            doc = json.loads(body or b"{}")
            raw = doc["records"] if isinstance(doc, dict) and "records" in doc else [doc]
            if not isinstance(raw, list) or not raw or len(raw) > MAX_RECORDS:
                raise ValueError
            records = [Record(str(r["id"]), dict(r.get("payload", {}))) for r in raw]
        except (ValueError, KeyError, TypeError):
            return _json(400, {"error": f"expected JSON with 1..{MAX_RECORDS} records "
                                        "of the form {\"id\":..., \"payload\":{...}}"})
        report = await self.app.pipeline.run(records)
        return _json(200, report.to_dict())
