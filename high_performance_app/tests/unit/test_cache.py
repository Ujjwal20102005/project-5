import pytest
from hpapp.cache.ttl_cache import TTLCache


class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_set_get_and_stats():
    c = TTLCache(2, 10)
    c.set("a", 1)
    assert c.get("a") == 1
    assert c.get("zzz") is None
    s = c.stats()
    assert (s["hits"], s["misses"], s["hit_rate"]) == (1, 1, 0.5)


def test_lru_eviction_order():
    c = TTLCache(2, 10)
    c.set("a", 1); c.set("b", 2)
    c.get("a")                      # a becomes most-recent
    c.set("c", 3)                   # evicts b
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3
    assert c.evictions == 1


def test_ttl_expiry():
    clk = FakeClock()
    c = TTLCache(5, 10, clock=clk)
    c.set("a", 1)
    clk.t = 11
    assert c.get("a") is None
    assert c.expirations == 1 and len(c) == 0


def test_custom_ttl_delete_clear():
    clk = FakeClock()
    c = TTLCache(5, 10, clock=clk)
    c.set("a", 1, ttl=1)
    clk.t = 2
    assert c.get("a") is None
    c.set("b", 2)
    assert c.delete("b") is True and c.delete("b") is False
    c.set("c", 3); c.clear()
    assert len(c) == 0


def test_invalid_size():
    with pytest.raises(ValueError):
        TTLCache(0)
