import asyncio
from concurrent.futures import ProcessPoolExecutor

import pytest
from hpapp.patterns.factory import StrategyFactory
from hpapp.patterns.observer import EventBus
from hpapp.patterns.strategies import (FastProcessingStrategy, IOBoundStrategy,
                                       ThoroughProcessingStrategy, ProcessingStrategy)


def test_factory_creates_and_lists():
    assert isinstance(StrategyFactory.create("fast"), FastProcessingStrategy)
    assert isinstance(StrategyFactory.create("io", latency=0.0), IOBoundStrategy)
    assert {"fast", "io", "thorough"} <= set(StrategyFactory.available())


def test_factory_unknown_and_register():
    with pytest.raises(ValueError):
        StrategyFactory.create("nope")

    class Custom(ProcessingStrategy):
        name = "custom"
        async def process(self, data): return {"digest": "x"}
    StrategyFactory.register("custom", Custom)
    assert StrategyFactory.create("custom").name == "custom"


def test_strategies_are_deterministic():
    async def go():
        a = await FastProcessingStrategy().process({"b": 1, "a": 2})
        b = await FastProcessingStrategy().process({"a": 2, "b": 1})
        io = await IOBoundStrategy(0).process({"a": 2, "b": 1})
        th = await ThoroughProcessingStrategy(rounds=10).process({"a": 2, "b": 1})
        return a, b, io, th
    a, b, io, th = asyncio.run(go())
    assert a["digest"] == b["digest"] == io["digest"]      # key order irrelevant
    assert th["digest"] != a["digest"] and th["status"] == "thorough_processed"


def test_thorough_with_process_pool():
    async def go():
        with ProcessPoolExecutor(max_workers=2) as pool:
            s = ThoroughProcessingStrategy(executor=pool, rounds=50)
            return await asyncio.gather(*(s.process({"i": i}) for i in range(4)))
    out = asyncio.run(go())
    assert len({o["digest"] for o in out}) == 4


def test_event_bus_sync_async_and_isolation():
    bus, seen = EventBus(), []
    async def acb(p): seen.append(("async", p))
    def scb(p): seen.append(("sync", p))
    def bad(p): raise RuntimeError("boom")
    for cb in (bad, scb, acb):
        bus.subscribe("e", cb)
    asyncio.run(bus.publish("e", 1))
    assert seen == [("sync", 1), ("async", 1)]           # bad subscriber didn't break others
    bus.unsubscribe("e", scb)
    bus.unsubscribe("e", scb)                              # idempotent
    seen.clear()
    asyncio.run(bus.publish("e", 2))
    assert seen == [("async", 2)]
    asyncio.run(bus.publish("no-subscribers"))
