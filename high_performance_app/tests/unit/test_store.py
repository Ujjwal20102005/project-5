import time
from hpapp.database.store import SQLiteStore


def rows(n, status="ok"):
    return [(f"id{i}", status, "fast", f"d{i}", 1.0, time.time() + i) for i in range(n)]


def test_insert_get_count(store):
    assert store.insert_many([]) == 0
    assert store.insert_many(rows(10)) == 10
    assert store.count() == 10
    assert store.get("id3")["digest"] == "d3"
    assert store.get("missing") is None


def test_replace_on_conflict(store):
    store.insert_many(rows(3))
    store.insert_many([("id1", "failed", "fast", None, 2.0, time.time())])
    assert store.count() == 3 and store.get("id1")["status"] == "failed"


def test_count_by_status_and_recent(store):
    store.insert_many(rows(5, "ok") + [("bad", "failed", "fast", None, 1.0, time.time())])
    assert store.count_by_status() == {"ok": 5, "failed": 1}
    recent = store.recent_by_status("ok", limit=2)
    assert [r["id"] for r in recent] == ["id4", "id3"]


def test_indexes_used_in_query_plan(store):
    plan = " ".join(store.explain_recent_by_status())
    assert "idx_results_status_created" in plan


def test_no_index_variant_scans(tmp_path):
    s = SQLiteStore(str(tmp_path / "n.db"), with_indexes=False)
    plan = " ".join(s.explain_recent_by_status())
    assert "idx_results" not in plan
    s.close()


def test_async_wrappers(store):
    import asyncio
    async def go():
        n = await store.insert_many_async(rows(4))
        return n, await store.count_by_status_async()
    assert asyncio.run(go()) == (4, {"ok": 4})
