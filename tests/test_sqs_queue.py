"""SqsJobQueue and the S3 photo hook, against a small fake of the SQS calls we use (no AWS needed)."""
import json

import httpx
import pytest

from genkart.ingest_worker import IngestWorker, PermanentError, S3Photos, is_permanent
from genkart.jobqueue import QueueFull
from genkart.sqs_queue import SqsJobQueue


class FakeSqs:
    """Just enough SQS FIFO: 5-minute dedup window, visibility timeout, receipt handles, per-queue message lists."""

    def __init__(self):
        self.t = 0.0
        self.q = {"main": [], "dlq": []}
        self.seen = {}
        self.n = 0

    def _name(self, url):
        return "dlq" if url.endswith("dlq") else "main"

    def send_message(self, QueueUrl, MessageBody, MessageGroupId, MessageDeduplicationId, MessageAttributes=None):
        name = self._name(QueueUrl)
        key = (name, MessageDeduplicationId)
        if key in self.seen and self.t - self.seen[key] < 300:
            return {"MessageId": "dup"}
        self.seen[key] = self.t
        self.n += 1
        self.q[name].append({"body": MessageBody, "group": MessageGroupId, "visible_at": 0.0, "receipt": None, "count": 0, "attrs": MessageAttributes or {}})
        return {"MessageId": str(self.n)}

    def receive_message(self, QueueUrl, MaxNumberOfMessages, VisibilityTimeout, WaitTimeSeconds, MessageSystemAttributeNames):
        out = []
        for m in self.q[self._name(QueueUrl)]:
            if len(out) < MaxNumberOfMessages and m["visible_at"] <= self.t:
                self.n += 1
                m["count"] += 1
                m["receipt"] = f"r{self.n}"
                m["visible_at"] = self.t + VisibilityTimeout
                out.append({"ReceiptHandle": m["receipt"], "Body": m["body"], "Attributes": {"ApproximateReceiveCount": str(m["count"]), "MessageGroupId": m["group"]}})
        return {"Messages": out}

    def delete_message(self, QueueUrl, ReceiptHandle):
        lst = self.q[self._name(QueueUrl)]
        for m in lst:
            if m["receipt"] == ReceiptHandle:
                lst.remove(m)
                return {}
        raise RuntimeError("ReceiptHandleIsInvalid")

    def change_message_visibility(self, QueueUrl, ReceiptHandle, VisibilityTimeout):
        for m in self.q[self._name(QueueUrl)]:
            if m["receipt"] == ReceiptHandle:
                m["visible_at"] = self.t + VisibilityTimeout

    def get_queue_attributes(self, QueueUrl, AttributeNames):
        lst = self.q[self._name(QueueUrl)]
        vis = sum(1 for m in lst if m["visible_at"] <= self.t)
        return {"Attributes": {"ApproximateNumberOfMessages": str(vis), "ApproximateNumberOfMessagesNotVisible": str(len(lst) - vis)}}


def make(max_depth=10**6):
    f = FakeSqs()
    return f, SqsJobQueue(f, "https://sqs/main", "https://sqs/dlq", max_depth=max_depth, clock=lambda: f.t)


def test_send_receive_delete_roundtrip():
    f, q = make()
    q.send({"id": "7"}, dedup="7")
    [m] = q.receive(5, 30)
    assert m["body"] == {"id": "7"} and m["receive_count"] == 1
    assert q.receive(5, 30) == []                       # hidden while in flight
    assert q.delete(m["receipt"]) is True
    assert q.stats()["waiting"] == 0 and q.stats()["in_flight"] == 0


def test_same_dedup_id_within_five_minutes_is_dropped_by_sqs():
    f, q = make()
    q.send({"id": "7"}, dedup="7")
    q.send({"id": "7"}, dedup="7")
    assert len(f.q["main"]) == 1
    f.t += 301
    q.send({"id": "7"}, dedup="7")
    assert len(f.q["main"]) == 2


def test_fail_with_backoff_delays_the_retry():
    f, q = make()
    q.send({"id": "1"}, dedup="1")
    [m] = q.receive(1, 20)
    q.fail(m["receipt"], "replica down", 8)
    f.t += 7
    assert q.receive(1, 20) == []
    f.t += 2
    [again] = q.receive(1, 20)
    assert again["receive_count"] == 2


def test_dead_now_copies_to_dlq_with_the_error_and_removes_the_original():
    f, q = make()
    q.send({"id": "9"}, dedup="9")
    [m] = q.receive(1, 20)
    q.dead_now(m["receipt"], "photo not found")
    assert f.q["main"] == []
    [d] = f.q["dlq"]
    assert json.loads(d["body"]) == {"id": "9"} and d["attrs"]["error"]["StringValue"] == "photo not found"


def test_delete_with_an_invalid_receipt_returns_false():
    _, q = make()
    assert q.delete("nope") is False


def test_backpressure_raises_queue_full():
    f, q = make(max_depth=2)
    q.send({"id": "1"}, "1")
    q.send({"id": "2"}, "2")
    f.t += 6                                            # the size check refreshes at most every 5 seconds
    with pytest.raises(QueueFull):
        q.send({"id": "3"}, "3")


def test_s3_photos_passes_local_paths_through_and_downloads_s3_ones(tmp_path):
    calls = []

    class S3:
        def download_file(self, bucket, key, dest):
            calls.append((bucket, key))
            open(dest, "wb").write(b"jpg")

    p = S3Photos(S3(), str(tmp_path))
    assert p("data/images/1.jpg") == "data/images/1.jpg"
    local = p("s3://b/ingest-photos/42.jpg")
    assert local.endswith(".jpg") and calls == [("b", "ingest-photos/42.jpg")]
    p("s3://b/ingest-photos/42.jpg")                    # second time: served from the local copy
    assert len(calls) == 1


def test_missing_photo_is_a_permanent_error_other_failures_are_not(tmp_path):
    class Err(Exception):
        def __init__(self, code):
            self.response = {"Error": {"Code": code}}

    class S3:
        def __init__(self, code):
            self.code = code

        def download_file(self, *a):
            raise Err(self.code)

    with pytest.raises(PermanentError):
        S3Photos(S3("404"), str(tmp_path))("s3://b/k/1.jpg")
    with pytest.raises(Err):
        S3Photos(S3("SlowDown"), str(tmp_path))("s3://b/k/2.jpg")
    assert is_permanent(PermanentError("x")) and not is_permanent(RuntimeError("x"))


def test_worker_dead_letters_a_missing_photo_at_once_and_acks_the_good_one(tmp_path):
    f, q = make()
    q.send({"id": "1", "image": "s3://b/p/1.jpg", "source": "marqo", "cluster": 1, "title": "good"}, "1")
    q.send({"id": "2", "image": "s3://b/p/missing.jpg", "source": "marqo", "cluster": 2, "title": "bad"}, "2")

    class S3:
        def download_file(self, bucket, key, dest):
            if "missing" in key:
                e = Exception("nope")
                e.response = {"Error": {"Code": "NoSuchKey"}}
                raise e
            open(dest, "wb").write(b"jpg")

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        if request.url.path == "/encode_images":
            return httpx.Response(200, json={"vectors": [[0.1, 0.2] for _ in body["paths"]]})
        return httpx.Response(200, json={"added": 1, "skipped": 0, "products": 1})

    w = IngestWorker(q, "http://enc", [["http://s0"]], batch=8, client=httpx.Client(transport=httpx.MockTransport(handler)), resolve_image=S3Photos(S3(), str(tmp_path)))
    assert w.step() == 2
    assert w.stats["acked"] == 1
    assert len(f.q["dlq"]) == 1 and json.loads(f.q["dlq"][0]["body"])["id"] == "2" and "photo not found" in f.q["dlq"][0]["attrs"]["error"]["StringValue"]
    assert f.q["main"] == []


def test_encoder_returning_too_few_vectors_falls_back_to_one_by_one(tmp_path):
    f, q = make()
    for i in (1, 2):
        q.send({"id": str(i), "image": f"data/{i}.jpg", "source": "marqo", "cluster": i, "title": "t"}, str(i))
    seen = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        if request.url.path == "/encode_images":
            seen.append(len(body["paths"]))
            n = 1 if len(body["paths"]) == 2 else len(body["paths"])   # a broken encoder: one vector short for the batch call only
            return httpx.Response(200, json={"vectors": [[0.1, 0.2]] * n})
        return httpx.Response(200, json={"added": 1, "skipped": 0, "products": 1})

    w = IngestWorker(q, "http://enc", [["http://s0"]], batch=8, client=httpx.Client(transport=httpx.MockTransport(handler)))
    w.step()
    assert w.stats["acked"] == 2 and seen == [2, 1, 1]


def test_changing_the_retry_delay_of_an_expired_message_is_not_fatal():
    f, q = make()
    q.send({"id": "1"}, "1")
    [m] = q.receive(1, 20)

    def boom(**kw):
        raise RuntimeError("InvalidParameterValue: message is not in flight")

    f.change_message_visibility = boom
    q.fail(m["receipt"], "replica down", 8)             # must log and return, not raise


def test_worker_skips_messages_it_can_no_longer_finish_inside_their_hiding_time(tmp_path):
    import time

    f, q = make()
    for i in (1, 2, 3):
        q.send({"id": str(i), "image": f"data/{i}.jpg", "source": "marqo", "cluster": i, "title": "t"}, str(i))

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        if request.url.path == "/encode_images":
            return httpx.Response(200, json={"vectors": [[0.1, 0.2]] * len(body["paths"])})
        time.sleep(0.15)                                 # every shard write is slow
        return httpx.Response(200, json={"added": 1, "skipped": 0, "products": 1})

    w = IngestWorker(q, "http://enc", [["http://s0"]], batch=8, visibility_s=0.25, client=httpx.Client(transport=httpx.MockTransport(handler)))
    w.step()
    assert w.stats["acked"] + w.stats.get("skipped_late", 0) == 3 and w.stats.get("skipped_late", 0) >= 1


def test_run_survives_an_unexpected_error_in_one_batch(monkeypatch):
    f, q = make()
    calls = {"n": 0}
    w = IngestWorker(q, "http://enc", [["http://s0"]], client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))

    def flaky_step():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("unexpected")
        raise KeyboardInterrupt                          # stop the loop from the outside after the second call

    w.step = flaky_step
    import genkart.ingest_worker as iw
    monkeypatch.setattr(iw.time, "sleep", lambda s: None)   # restored automatically after this test
    with pytest.raises(KeyboardInterrupt):
        w.run()
    assert calls["n"] == 2                               # the first error did not end the loop


def test_two_photos_with_the_same_file_name_in_different_folders_do_not_share_a_cache_file(tmp_path):
    class S3:
        def download_file(self, bucket, key, dest):
            with open(dest, "w") as f:
                f.write(key)

    p = S3Photos(S3(), str(tmp_path))
    a, b = p("s3://b/one/1.jpg"), p("s3://b/two/1.jpg")
    assert a != b and open(a).read() == "one/1.jpg" and open(b).read() == "two/1.jpg"


def test_remembered_receipts_stay_bounded():
    f, q = make()
    for i in range(2600):
        q.send({"id": str(i)}, str(i))
    for _ in range(300):
        q.receive(10, 30)
    assert len(q._bodies) <= 2000


def test_one_unreadable_message_goes_to_the_dead_letter_queue_and_the_rest_are_still_delivered():
    f, q = make()
    f.send_message("https://sqs/main", "this is not json", "g1", "d1")
    q.send({"id": "11"}, dedup="11")
    q.send({"id": "12"}, dedup="12")
    got = q.receive(10, 30)
    assert sorted(m["body"]["id"] for m in got) == ["11", "12"]       # the batch was not lost
    [dead] = f.q["dlq"]
    assert dead["body"] == "this is not json" and "unreadable" in dead["attrs"]["error"]["StringValue"]
    assert all(m["body"] != "this is not json" for m in f.q["main"])  # and the original is gone from the main queue
