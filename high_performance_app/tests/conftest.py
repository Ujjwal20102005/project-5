import pytest

from hpapp.cache.ttl_cache import TTLCache
from hpapp.database.store import SQLiteStore
from hpapp.models import Record


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(str(tmp_path / "t.db"), pool_size=3)
    yield s
    s.close()


@pytest.fixture
def cache():
    return TTLCache(maxsize=100, ttl=60)


def make_records(n, prefix="r"):
    return [Record(f"{prefix}{i}", {"n": i}) for i in range(n)]
