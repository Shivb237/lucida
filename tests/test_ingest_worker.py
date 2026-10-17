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
        body = json.loads(request.content)
        self.calls.append(url)
        if url.endswith("/encode_images"):
            if any("missing" in p for p in body["paths"]):
                return httpx.Response(422, json={"detail": "not a readable file"})
            return httpx.Response(200, json={"vectors": [[0.1, 0.2] for _ in body["paths"]]})
        host = url.split("/ingest")[0]
        if host in self.down:
            return httpx.Response(503, json={})
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
