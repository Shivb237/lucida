"""Adding products through the queue: every replica gets it, retries do not duplicate, a bad photo is parked."""
import json

import httpx

from genkart.ingest_worker import IngestWorker
from genkart.jobqueue import JobQueue


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


class Fake:
    """Fake encoder + shard replicas behind one httpx mock transport."""

    def __init__(self, down=()):
        self.down, self.added, self.calls = set(down), {}, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if url.endswith("/health"):
            return httpx.Response(503 if url.removesuffix("/health") in self.down else 200, json={"ok": True})
        body = json.loads(request.content)
        if url.endswith("/encode_images"):
            if any("missing" in p for p in body["paths"]):
                return httpx.Response(422, json={"detail": "not a readable file"})
            return httpx.Response(200, json={"vectors": [[0.1, 0.2] for _ in body["paths"]]})
        host = url.split("/ingest")[0]
        self.tokens = getattr(self, "tokens", []) + [request.headers.get("x-genkart-token")]
        if host in self.down:
            return httpx.Response(503, json={})
        if getattr(self, "want_token", None) and request.headers.get("x-genkart-token") != self.want_token:
            return httpx.Response(401, json={"detail": "missing or wrong shard token"})
        for it in body["items"]:
            self.added.setdefault(host, {})[it["id"]] = it          # idempotent by id, like the real shard
        return httpx.Response(200, json={"added": 1})


def _setup(tmp_path, fake, groups=(("http://a1", "http://a2"), ("http://b1", "http://b2"))):
    clock = Clock()
    q = JobQueue(str(tmp_path / "q.db"), clock=clock, max_receives=3)
    w = IngestWorker(q, "http://enc", [list(g) for g in groups], batch=8, visibility_s=10, client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    return q, w, clock


def _msg(i, image="data/x.jpg"):
    return {"id": str(i), "source": "marqo", "gender": "", "cluster": i, "title": f"t{i}", "image": image}


def test_a_product_goes_to_every_replica_of_its_shard_and_is_acked(tmp_path):
    fake = Fake()
    q, w, _ = _setup(tmp_path, fake)
    q.send(_msg(4))                      # 4 % 2 = shard 0 = a1 + a2
    q.send(_msg(7))                      # shard 1 = b1 + b2
    assert w.step() == 2
    assert set(fake.added["http://a1"]) == {"4"} == set(fake.added["http://a2"])
    assert set(fake.added["http://b1"]) == {"7"} == set(fake.added["http://b2"])
    assert q.stats() == {"waiting": 0, "in_flight": 0, "dead": 0, "max_depth": 1000}


def test_one_replica_down_means_no_ack_then_a_retry_completes_it_without_duplicates(tmp_path):
    fake = Fake(down={"http://a2"})
    q, w, clock = _setup(tmp_path, fake)
    q.send(_msg(4))
    w.step()
    assert "4" in fake.added["http://a1"] and "http://a2" not in fake.added      # one copy written, the other not
    assert q.stats()["in_flight"] == 1 and w.stats["acked"] == 0                  # not acknowledged
    fake.down.clear()
    clock.t += 11                                                                  # the message reappears
    w.step()
    assert len(fake.added["http://a1"]) == 1 and set(fake.added["http://a2"]) == {"4"}   # a1 saw it twice but holds it once
    assert q.stats()["waiting"] == 0 and q.stats()["in_flight"] == 0 and w.stats["acked"] == 1


def test_a_bad_photo_is_isolated_and_ends_in_the_dead_letter_queue(tmp_path):
    fake = Fake()
    q, w, clock = _setup(tmp_path, fake)
    q.send(_msg(2))
    q.send(_msg(3, image="data/missing.jpg"))
    q.send(_msg(5))
    for _ in range(4):
        w.step()
        clock.t += 11
    assert {"2"} <= set(fake.added["http://a1"]) and {"5"} <= set(fake.added["http://b1"])   # the good ones were not held up by the bad one
    dead = q.dead_letters()
    assert len(dead) == 1 and dead[0]["body"]["id"] == "3" and "embed" in dead[0]["error"]


def test_the_same_product_sent_twice_is_added_once(tmp_path):
    fake = Fake()
    q, w, _ = _setup(tmp_path, fake)
    assert q.send(_msg(4), dedup="p4") and not q.send(_msg(4), dedup="p4")
    w.step()
    assert len(fake.added["http://a1"]) == 1


def test_drain_returns_when_the_queue_is_empty(tmp_path):
    fake = Fake()
    q, w, _ = _setup(tmp_path, fake)
    for i in (2, 4, 6):
        q.send(_msg(i))
    w.run(drain=True, idle_s=0)
    assert w.stats["acked"] == 3


def test_a_down_replica_is_retried_with_backoff_not_at_once_and_a_permanent_error_is_not_retried_at_all(tmp_path):
    fake = Fake(down={"http://a2"})
    q, w, clock = _setup(tmp_path, fake)
    q.send(_msg(4))                                              # needs replica a2, which is down
    q.send(_msg(3, image="data/missing.jpg"))                    # permanent: the photo does not exist
    w.step()
    assert q.stats()["dead"] == 1 and q.dead_letters()[0]["body"]["id"] == "3"       # parked at once, no retries
    clock.t += 1
    assert q.receive(5) == []                                    # the transient failure is backing off (2 s after the first try)
    fake.down.clear()
    clock.t += 3
    w.step()
    assert w.stats["acked"] == 1 and set(fake.added["http://a2"]) == {"4"}


def test_a_down_replica_pauses_receiving_instead_of_burning_the_retry_budget(tmp_path):
    fake = Fake(down={"http://a2"})
    q, w, clock = _setup(tmp_path, fake)
    q.send(_msg(4))
    w.step()                                                             # the write to a2 fails: a2 is marked down
    assert w.down == {"http://a2"}
    for _ in range(5):
        clock.t += 100                                                   # long past every backoff: the message is visible again
        assert w.step() == 0                                             # paused: nothing received while a2 is down
    assert q.stats()["waiting"] == 1 and q.stats()["dead"] == 0 and w.stats["paused"] == 5
    fake.down.clear()
    assert w.step() == 1 and w.stats["acked"] == 1 and not w.down


def test_products_for_one_shard_go_in_one_request_of_at_most_32_and_carry_the_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GENKART_SHARD_TOKEN", "tok")
    fake = Fake()
    clock = Clock()
    q = JobQueue(str(tmp_path / "q.db"), clock=clock, max_receives=3)
    w = IngestWorker(q, "http://enc", [["http://a1"]], batch=40, visibility_s=10, client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    for i in range(40):
        q.send(_msg(i))
    assert w.step() == 40 and w.stats["acked"] == 40
    ingests = [u for u in fake.calls if u.endswith("/ingest")]
    assert len(ingests) == 2 and len(fake.added["http://a1"]) == 40            # 32 + 8, not 40 requests
    assert set(fake.tokens) == {"tok"}


def test_one_refused_product_in_a_batch_does_not_hold_up_the_others(tmp_path):
    fake = Fake()
    real = fake.handler

    def handler(request):
        if request.url.path == "/ingest" and any(it["id"] == "6" for it in json.loads(request.content)["items"]):
            return httpx.Response(422, json={"detail": "bad vector"})
        return real(request)

    clock = Clock()
    q = JobQueue(str(tmp_path / "q.db"), clock=clock, max_receives=3)
    w = IngestWorker(q, "http://enc", [["http://a1"]], batch=8, visibility_s=10, client=httpx.Client(transport=httpx.MockTransport(handler)))
    for i in (2, 4, 6):
        q.send(_msg(i))
    w.step()
    assert set(fake.added["http://a1"]) == {"2", "4"} and w.stats["acked"] == 2 and not w.down


def test_a_photo_fetched_from_s3_is_deleted_once_embedded(tmp_path):
    from genkart.ingest_worker import S3Photos

    class S3:
        def download_file(self, bucket, key, dest):
            open(dest, "wb").write(b"jpg")

    photos = S3Photos(S3(), str(tmp_path / "photos"))
    fake = Fake()
    clock = Clock()
    q = JobQueue(str(tmp_path / "q.db"), clock=clock, max_receives=3)
    w = IngestWorker(q, "http://enc", [["http://a1"]], client=httpx.Client(transport=httpx.MockTransport(fake.handler)), resolve_image=photos)
    q.send(_msg(2, image="s3://bucket/p/2.jpg"))
    w.step()
    assert w.stats["acked"] == 1 and list((tmp_path / "photos").iterdir()) == []
    keep = tmp_path / "keep.jpg"
    keep.write_bytes(b"x")
    photos.cleanup(str(keep))                                            # a local path from the producer is never deleted
    assert keep.exists()


def test_a_replica_refusing_the_token_pauses_the_queue_instead_of_burning_every_retry(tmp_path):
    fake = Fake()
    fake.want_token = "right"
    q, w, clock = _setup(tmp_path, fake)
    w.headers = {"x-genkart-token": "wrong"}
    for i in range(4):
        q.send(_msg(i))
    w.step()                                       # the first batch fails once and marks the replicas down
    for _ in range(5):
        clock.t += 60                              # well past every backoff: a worker that did not pause would burn receives here
        assert w.step() == 0
    assert q.stats()["dead"] == 0 and w.stats.get("paused", 0) == 5
    w.headers = {"x-genkart-token": "right"}       # the token is fixed: the replicas answer the empty probe, and the queue drains
    clock.t += 60
    while w.step():
        clock.t += 60
    assert q.stats()["waiting"] == 0 and q.stats()["dead"] == 0 and set(fake.added["http://a1"]) == {"0", "2"}
