#!/usr/bin/env python3
"""Tiny asyncio load generator against a running server.
Usage: python scripts/load_test.py [host] [port] [requests] [concurrency]"""
import asyncio, json, sys, time

async def one(host, port, i):
    body = json.dumps({"records": [{"id": f"lt{i}-{j}", "payload": {"i": i, "j": j}} for j in range(10)]}).encode()
    t0 = time.perf_counter()
    r, w = await asyncio.open_connection(host, port)
    w.write(f"POST /process HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
    await w.drain()
    head = (await r.read()).split(b"\r\n", 1)[0]
    w.close()
    return int(head.split()[1]), (time.perf_counter() - t0) * 1000

async def main(host="127.0.0.1", port=8080, n=500, conc=50):
    sem = asyncio.Semaphore(conc)
    async def guarded(i):
        async with sem:
            return await one(host, port, i)
    t0 = time.perf_counter()
    res = await asyncio.gather(*(guarded(i) for i in range(n)))
    el = time.perf_counter() - t0
    lat = sorted(l for _, l in res)
    codes = {}
    for c, _ in res: codes[c] = codes.get(c, 0) + 1
    print(f"requests={n} concurrency={conc} elapsed={el:.2f}s rps={n/el:.0f} codes={codes}")
    print(f"latency ms: p50={lat[n//2]:.1f} p95={lat[int(n*.95)]:.1f} p99={lat[int(n*.99)]:.1f}")

if __name__ == "__main__":
    a = sys.argv[1:]
    asyncio.run(main(*(a[:1] or ["127.0.0.1"]), *(int(x) for x in a[1:])))
