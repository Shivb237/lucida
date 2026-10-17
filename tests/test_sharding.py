"""Splitting products over shards gives exactly the single-process answer for any shard count."""
import json

import numpy as np
import pytest

from genkart.sharding import ShardData, merge_route, shard_of, split


def _data(n=400, d=16, seed=0):
    rng = np.random.default_rng(seed)
    v = rng.normal(size=(n, d)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    src = rng.choice(["marqo", "kaggle", "myntra2", "mens3"], n, p=[0.4, 0.3, 0.2, 0.1])
    gender = np.where(src == "myntra2", "Women", np.where(src == "mens3", "Men", rng.choice(["Men", "Women", "Unisex", ""], n)))
    cluster = np.arange(n) // 2                        # every product has one near-copy
    ids = (10**15 + rng.permutation(n) * 7919).tolist()
    return ShardData(ids, v, src, gender, cluster, [f"t{i}" for i in range(n)]), rng


def test_every_product_lives_in_exactly_one_shard():
    data, _ = _data()
    shards = split(data, 4)
    assert sum(len(s) for s in shards) == len(data) and len({i for s in shards for i in s.ids}) == len(data)
    assert all(shard_of(i, 4) == k for k, s in enumerate(shards) for i in s.ids)


def test_sharded_answer_equals_single_shard_answer_for_any_shard_count():
    data, rng = _data()
    for trial in range(30):
        q = rng.normal(size=16).astype(np.float32)
        q /= np.linalg.norm(q)
        gender = [None, "men", "women"][trial % 3]
        theta = [0.0, 10.0][trial % 2]                       # 0.0: general always wins, 10.0: always fall back to specialists
        want = merge_route([data.search(q, gender)], 4, theta)
        for n in (2, 3, 8):
            got = merge_route([s.search(q, gender) for s in split(data, n)], 4, theta)
            assert [c.id for c in got] == [c.id for c in want], (trial, n)


def test_duplicates_never_appear_twice_and_gender_is_respected():
    data, rng = _data()
    q = rng.normal(size=16).astype(np.float32)
    out = merge_route([s.search(q, "men") for s in split(data, 4)], 4, theta=10.0)
    assert len({c.cluster for c in out}) == len(out)
    assert all(data.gender[data.ids.index(c.id)] in {"Men", "Unisex", ""} for c in out)


def test_shard_worker_answers_carry_the_catalogue_name():
    from fastapi.testclient import TestClient

    from genkart.shard_worker import make_app

    data, rng = _data(n=60)
    client = TestClient(make_app(0, data))
    q = rng.normal(size=16).astype(np.float32)
    body = client.post("/search", json={"vector": q.tolist(), "gender": None, "m": 5}).json()
    assert body["shard"] == 0
    for src, cands in body["candidates"].items():
        assert all(c["source"] == src and isinstance(c["id"], str) for c in cands)


def test_adding_products_is_idempotent_and_they_become_searchable():
    data, rng = _data(n=60)
    q = rng.normal(size=16).astype(np.float32)
    q /= np.linalg.norm(q)
    item = {"id": "17777777777777777777", "vector": q.tolist(), "source": "marqo", "gender": "", "cluster": 99999, "title": "late arrival"}
    assert data.add([item]) == (1, 0)
    assert data.add([item]) == (0, 1)                      # a retried message changes nothing
    assert len(data) == 61 and data.ids.count(int(item["id"])) == 1
    best = data.search(q, None)["marqo"][0]
    assert best.id == int(item["id"]) and best.title == "late arrival"


def test_ingest_endpoint_logs_first_and_a_restarted_worker_keeps_the_products(tmp_path):
    from fastapi.testclient import TestClient

    from genkart.shard_worker import make_app

    data, rng = _data(n=60)
    log = str(tmp_path / "added.jsonl")
    body = {"items": [{"id": "5", "vector": rng.normal(size=16).tolist(), "source": "kaggle", "gender": "Men", "cluster": 5, "title": "new"}]}
    c = TestClient(make_app(0, data, log))
    assert c.post("/ingest", json=body).json()["added"] == 1
    assert c.post("/ingest", json=body).json() == {"added": 0, "skipped": 1, "products": 61}
    assert sum(1 for _ in open(log)) == 1                  # the retry was not logged twice
    data2, _ = _data(n=60)                                 # restart: base file again, then replay the log
    c2 = TestClient(make_app(0, data2, log))
    health = c2.get("/health").json()
    assert health["products"] == 61 and health["replayed"] == 1


def test_an_id_outside_64_bits_is_rejected_with_a_clear_error():
    import pytest
    from fastapi.testclient import TestClient

    from genkart.shard_worker import make_app

    data, rng = _data(n=30)
    with pytest.raises(ValueError):
        data.add([{"id": str(2**64), "vector": [0.0] * 16, "source": "marqo", "gender": "", "cluster": 1, "title": "x"}])
    r = TestClient(make_app(0, data)).post("/ingest", json={"items": [{"id": str(2**64), "vector": [0.0] * 16, "source": "marqo", "cluster": 1, "title": "x"}]})
    assert r.status_code == 422


# ---- a malformed product must never corrupt a shard or poison its log
def _shard():
    return ShardData([1, 2], np.eye(2, 4, dtype=np.float32), ["marqo"] * 2, ["men"] * 2, [0, 1], ["a", "b"])


def _item(pid, vec):
    return {"id": str(pid), "vector": vec, "source": "marqo", "gender": "men", "cluster": pid, "title": f"p{pid}"}


def test_a_bad_vector_is_refused_and_leaves_the_shard_exactly_as_it_was():
    d = _shard()
    for bad in ([1, 0, 0], [1, 0, 0, float("nan")], [1, 0, 0, 0, 0]):
        with pytest.raises(ValueError):
            d.add([_item(3, bad)])
    assert d.ids == [1, 2] and len(d.vecs) == 2 and 3 not in d._id_set
    d.add([_item(4, [0, 0, 1, 0])])                                    # the next good product still gets its own id
    top = d.search(np.array([0, 0, 1, 0], dtype=np.float32))["marqo"][0]
    assert top.id == 4 and top.title == "p4"


def test_a_batch_with_one_bad_item_adds_nothing():
    d = _shard()
    with pytest.raises(ValueError):
        d.add([_item(5, [0, 0, 1, 0]), _item(6, [1])])
    assert d.ids == [1, 2] and 5 not in d._id_set


def test_saved_shard_files_load_without_pickle(tmp_path):
    d = _shard()
    d.save(str(tmp_path / "s.npz"))
    back = ShardData.load(str(tmp_path / "s.npz"))             # load refuses pickle, so this also proves nothing in the file needs it
    assert back.ids == [1, 2] and back.titles == ["a", "b"]


def test_worker_refuses_a_bad_item_before_logging_it_and_survives_a_damaged_log(tmp_path):
    from fastapi.testclient import TestClient

    from genkart.shard_worker import make_app
    log = tmp_path / "added.jsonl"
    client = TestClient(make_app(0, _shard(), str(log)))
    r = client.post("/ingest", json={"items": [{**_item(7, [1, 2, 3])}]})
    assert r.status_code == 422
    assert not log.exists() or log.read_text() == ""             # nothing was written where a restart would replay it
    assert client.post("/ingest", json={"items": [_item(8, [0, 0, 1, 0])]}).json()["added"] == 1
    log.write_text(log.read_text() + "not json at all\n" + json.dumps(_item(9, [1, 2])) + "\n")   # a damaged line and a wrong-size one
    h = TestClient(make_app(0, _shard(), str(log))).get("/health").json()
    assert h["replayed"] == 1 and h["bad_log_lines"] == 2          # the worker starts, keeps the good product, and says what it skipped


def test_the_admin_delay_route_exists_only_when_enabled(monkeypatch):
    from fastapi.testclient import TestClient

    from genkart.shard_worker import make_app
    monkeypatch.delenv("GENKART_ADMIN", raising=False)
    assert TestClient(make_app(0, _shard())).post("/admin/delay", json={"ms": 5}).status_code == 404
    monkeypatch.setenv("GENKART_ADMIN", "1")
    assert TestClient(make_app(0, _shard())).post("/admin/delay", json={"ms": 5}).status_code == 200
