import asyncio
import pytest
from hpapp.services.resilience import CircuitBreaker, CircuitOpenError, TokenBucket


class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


async def ok(): return "ok"
async def boom(): raise RuntimeError("x")


def test_breaker_opens_then_recovers():
    clk = Clock()
    cb = CircuitBreaker(2, 10, clock=clk)

    async def go():
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(boom)
        assert cb.state == "open"
        with pytest.raises(CircuitOpenError):
            await cb.call(ok)
        clk.t = 11
        assert await cb.call(ok) == "ok"            # half-open probe succeeds
        assert cb.state == "closed" and cb.failures == 0
    asyncio.run(go())


def test_breaker_half_open_failure_reopens():
    clk = Clock()
    cb = CircuitBreaker(1, 5, clock=clk)

    async def go():
        with pytest.raises(RuntimeError):
            await cb.call(boom)
        clk.t = 6
        with pytest.raises(RuntimeError):
            await cb.call(boom)
        assert cb.state == "open"
    asyncio.run(go())


def test_token_bucket_refill():
    clk = Clock()
    tb = TokenBucket(rate=2, capacity=3, clock=clk)
    assert [tb.allow() for _ in range(4)] == [True, True, True, False]
    clk.t = 1.0                                      # +2 tokens
    assert tb.allow() and tb.allow() and not tb.allow()
    clk.t = 100                                      # capped at capacity
    assert sum(tb.allow() for _ in range(10)) == 3
