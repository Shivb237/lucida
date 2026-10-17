"""The local queue: hiding time, acknowledge, dead-letter after too many tries, repeated keys ignored."""
import pytest

from genkart.jobqueue import JobQueue, QueueFull


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _q(tmp_path, **kw):
    clock = Clock()
    return JobQueue(str(tmp_path / "q.db"), clock=clock, **kw), clock


def test_a_received_message_is_hidden_until_its_timeout_then_reappears(tmp_path):
    q, clock = _q(tmp_path)
    q.send({"id": 1})
    first = q.receive(5, visibility_s=30)
    assert len(first) == 1 and first[0]["receive_count"] == 1
    assert q.receive(5, visibility_s=30) == []                 # in flight: invisible
    clock.t += 31                                              # the worker died; nobody acked
    again = q.receive(5, visibility_s=30)
    assert len(again) == 1 and again[0]["receive_count"] == 2 and again[0]["body"] == {"id": 1}


def test_ack_removes_the_message_for_good(tmp_path):
    q, clock = _q(tmp_path)
    q.send({"id": 1})
    m = q.receive(1)[0]
    assert q.delete(m["receipt"]) is True and q.delete(m["receipt"]) is False
    clock.t += 1000
    assert q.receive(5) == [] and q.stats()["waiting"] == 0


def test_poison_message_goes_to_the_dead_letter_queue_after_max_receives(tmp_path):
    q, clock = _q(tmp_path, max_receives=3)
    q.send({"id": "bad"})
    q.send({"id": "good"})
    for _ in range(3):
        for m in q.receive(5, visibility_s=10):
            if m["body"]["id"] == "bad":
                q.fail(m["receipt"], "no such file")
            else:
                q.delete(m["receipt"])
        clock.t += 11
    assert q.receive(5) == []
    dead = q.dead_letters()
    assert len(dead) == 1 and dead[0]["body"] == {"id": "bad"} and dead[0]["error"] == "no such file" and q.stats()["dead"] == 1


def test_sending_the_same_dedup_key_twice_adds_one_message(tmp_path):
    q, _ = _q(tmp_path)
    assert q.send({"id": 1}, dedup="p1") is True and q.send({"id": 1}, dedup="p1") is False
    assert q.stats()["waiting"] == 1


def test_backpressure_when_the_queue_is_full_and_room_after_an_ack(tmp_path):
    q, _ = _q(tmp_path, max_depth=2)
    q.send({"id": 1})
    q.send({"id": 2})
    with pytest.raises(QueueFull):
        q.send({"id": 3})
    q.delete(q.receive(1)[0]["receipt"])
    q.send({"id": 3})
    assert q.stats()["waiting"] == 2


def test_messages_survive_a_restart(tmp_path):
    q, clock = _q(tmp_path)
    q.send({"id": 1}, dedup="a")
    q.receive(1, visibility_s=5)
    del q
    q2 = JobQueue(str(tmp_path / "q.db"), clock=clock)
    clock.t += 6
    assert [m["body"] for m in q2.receive(5)] == [{"id": 1}]
    assert q2.send({"id": 1}, dedup="a") is False             # the dedup memory also survived


def test_dedup_survives_the_ack_for_the_window_then_expires(tmp_path):
    q, clock = _q(tmp_path)
    assert q.send({"id": 1}, dedup="p1") is True
    q.delete(q.receive(1)[0]["receipt"])                       # acknowledged and gone from the queue
    assert q.send({"id": 1}, dedup="p1") is False              # a late duplicate from the producer is still ignored
    clock.t += 301                                             # past the 300 s window
    assert q.send({"id": 1}, dedup="p1") is True


def test_dead_now_parks_a_message_immediately(tmp_path):
    q, clock = _q(tmp_path)
    q.send({"id": 1})
    m = q.receive(1)[0]
    q.dead_now(m["receipt"], "no such file")
    assert q.stats()["dead"] == 1 and q.receive(5) == []
    clock.t += 1000
    assert q.receive(5) == []


def test_fail_with_backoff_delays_the_retry_and_redrive_gives_dead_letters_a_fresh_start(tmp_path):
    q, clock = _q(tmp_path, max_receives=2)
    q.send({"id": 1})
    q.fail(q.receive(1, visibility_s=1)[0]["receipt"], "replica down", retry_after_s=20)
    clock.t += 5
    assert q.receive(5) == []                                  # still backing off
    clock.t += 16
    m = q.receive(5, visibility_s=1)
    assert len(m) == 1 and m[0]["receive_count"] == 2
    clock.t += 2
    assert q.receive(5) == [] and q.stats()["dead"] == 1       # a third hand-out would exceed max_receives: dead-lettered
    assert q.redrive("write") == 0 and q.redrive() == 1        # the prefix did not match (no error text yet recorded); redrive all
    again = q.receive(5)
    assert len(again) == 1 and again[0]["receive_count"] == 1
