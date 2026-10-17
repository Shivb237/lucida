"""Ingest worker: takes new-product messages from the job queue, embeds the photo, adds the product to EVERY replica of its shard.

A message is acknowledged only when every replica of the owning shard accepted it. Failures are of two kinds:
  permanent (the server says the request itself is wrong: a missing photo, an invalid id)  -> dead-letter queue at once
  transient (a replica or the encoder is unreachable, a timeout)                           -> retried later with exponential backoff
After max_receives tries a message lands in the dead-letter queue anyway; JobQueue.redrive() replays it once the cause is fixed.
Adding is idempotent on the shard side, so retries and duplicates are harmless.
Run on a laptop:  PYTHONPATH=src .venv/bin/python -m genkart.ingest_worker --queue data/ingest/queue.db [--drain]
Run on AWS:       python -m genkart.ingest_worker --sqs-queue URL --sqs-dlq URL --region ap-south-1   (shards from $SHARD_URLS; photos named s3://... are fetched first)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import time
import traceback

import httpx

from genkart.jobqueue import JobQueue

DEFAULT_SHARDS = "http://127.0.0.1:9101|http://127.0.0.1:9111,http://127.0.0.1:9102|http://127.0.0.1:9112,http://127.0.0.1:9103|http://127.0.0.1:9113,http://127.0.0.1:9104|http://127.0.0.1:9114"


class PermanentError(Exception):
    """Retrying cannot help (for example the photo does not exist): the message goes to the dead-letter queue at once."""


def is_permanent(error: Exception) -> bool:
    """The server understood the request and refused it (400/404/422), or we already know it can never work: trying again cannot succeed."""
    if isinstance(error, PermanentError):
        return True
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (400, 404, 422)


class S3Photos:
    """Turns "s3://bucket/key.jpg" into a local file under data/ (the encoder only reads files under data/). Other paths pass through unchanged."""

    def __init__(self, s3_client, local_dir: str = "data/ingest-photos"):
        self.s3, self.dir = s3_client, pathlib.Path(local_dir)

    def __call__(self, image: str) -> str:
        if not image.startswith("s3://"):
            return image
        bucket, _, key = image[5:].partition("/")
        if not bucket or not key:
            raise PermanentError(f"not a valid s3 address: {image}")
        # named after the whole address, not just the file name: s3://b/a/1.jpg and s3://b/c/1.jpg are different photos
        local = self.dir / (hashlib.sha256(image.encode()).hexdigest()[:24] + pathlib.PurePosixPath(key).suffix)
        if local.exists():
            return str(local)
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            self.s3.download_file(bucket, key, str(local))
        except Exception as e:  # noqa: BLE001
            code = str(getattr(e, "response", {}).get("Error", {}).get("Code", ""))
            if code in ("404", "NoSuchKey", "NoSuchBucket"):
                raise PermanentError(f"photo not found: {image}") from e
            raise                                      # anything else (network, throttling, permissions) is treated as temporary
        return str(local)


def backoff_s(receive_count: int, base: float = 2.0, cap: float = 60.0) -> float:
    return min(cap, base * 2 ** max(0, receive_count - 1))


def parse_groups(spec: str) -> list[list[str]]:
    return [[u.strip() for u in g.split("|") if u.strip()] for g in spec.split(",") if g.strip()]


class IngestWorker:
    def __init__(self, queue: JobQueue, encoder_url: str, groups: list[list[str]], batch: int = 8, visibility_s: float = 60.0, timeout_s: float = 10.0, client: httpx.Client | None = None, resolve_image=None):
        self.queue, self.encoder_url, self.groups, self.batch, self.visibility_s = queue, encoder_url, groups, batch, visibility_s
        self.resolve_image = resolve_image or (lambda image: image)
        self.http = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=2.0))   # a switched-off computer never answers: notice in 2 s, not 10 s
        self.stats = {"acked": 0, "failed_attempts": 0, "batches": 0}

    def _embed(self, paths: list[str]) -> list[list[float]]:
        r = self.http.post(f"{self.encoder_url}/encode_images", json={"paths": [self.resolve_image(p) for p in paths]})
        r.raise_for_status()
        return r.json()["vectors"]

    def _write(self, item: dict) -> None:
        """Add the item to every replica of its shard; raises unless all of them accepted it."""
        group = self.groups[int(item["id"]) % len(self.groups)]
        errors = []
        for url in group:
            try:
                r = self.http.post(f"{url}/ingest", json={"items": [item]})
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                errors.append(f"{url}: {e}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def step(self) -> int:
        """Handle one batch. Returns the number of messages received (0 = the queue is empty or everything is in flight)."""
        msgs = self.queue.receive(self.batch, self.visibility_s)
        if not msgs:
            return 0
        self.stats["batches"] += 1
        t_batch, acked_before, failed_before = time.time(), self.stats["acked"], self.stats["failed_attempts"]
        late = lambda: time.time() - t_batch > self.visibility_s * 0.8   # noqa: E731  past this, the hiding time is nearly up: the message is about to reappear on its own
        vectors: dict[str, list[float]] = {}
        failed: set[str] = set()
        try:                                         # fast path: one call for the whole batch
            for m, v in zip(msgs, self._embed([m["body"]["image"] for m in msgs]), strict=True):   # strict: fewer vectors than photos must fail loudly, not drop messages
                vectors[m["receipt"]] = v
        except Exception:  # noqa: BLE001           # a bad photo poisons the batch call: embed one by one to find which message it is
            for m in msgs:
                try:
                    vectors[m["receipt"]] = self._embed([m["body"]["image"]])[0]
                except Exception as e:  # noqa: BLE001
                    failed.add(m["receipt"])
                    if is_permanent(e):
                        self.queue.dead_now(m["receipt"], f"embed: {e}")
                    else:
                        self.queue.fail(m["receipt"], f"embed: {e}", backoff_s(m["receive_count"]))
        for m in msgs:
            if m["receipt"] not in vectors:
                self.stats["failed_attempts"] += 1
                continue
            if late():                                  # too slow to finish this one safely: leave it, it reappears in a moment
                self.stats["skipped_late"] = self.stats.get("skipped_late", 0) + 1
                continue
            body = m["body"]
            try:
                self._write({"id": body["id"], "vector": vectors[m["receipt"]], "source": body["source"], "gender": body.get("gender", ""),
                             "cluster": body["cluster"], "title": body["title"]})
                if self.queue.delete(m["receipt"]):
                    self.stats["acked"] += 1
                else:                                   # written to every replica but the acknowledgement was refused: it will be handled again (harmless, adding is idempotent)
                    self.stats["delete_failed"] = self.stats.get("delete_failed", 0) + 1
            except Exception as e:  # noqa: BLE001
                self.queue.fail(m["receipt"], f"write: {e}", backoff_s(m["receive_count"]))
                self.stats["failed_attempts"] += 1
        # one JSON line per batch: journald keeps it, and CloudWatch can read it later
        print(json.dumps({"event": "batch", "received": len(msgs), "acked": self.stats["acked"] - acked_before,
                          "failed": self.stats["failed_attempts"] - failed_before, "seconds": round(time.time() - t_batch, 2),
                          "max_receive_count": max(m["receive_count"] for m in msgs)}), flush=True)
        return len(msgs)

    def run(self, drain: bool = False, idle_s: float = 0.5, max_idle_cycles: int = 40) -> None:
        idle = 0
        while True:
            try:
                handled = self.step()
            except Exception as e:  # noqa: BLE001  one bad batch (an unexpected AWS answer, a full disk) must not kill the worker: log it and carry on
                print(json.dumps({"event": "step_error", "error": f"{type(e).__name__}: {str(e)[:300]}"}), flush=True)
                traceback.print_exc()
                time.sleep(2)
                continue
            if handled:
                idle = 0
                continue
            if drain:
                s = self.queue.stats()
                if s["waiting"] == 0 and s["in_flight"] == 0:
                    return
            idle += 1
            if drain and idle > max_idle_cycles * 10:
                return
            time.sleep(idle_s)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default="data/ingest/queue.db", help="laptop queue file (SQLite)")
    ap.add_argument("--sqs-queue", default=None, help="SQS queue URL: use Amazon SQS instead of the laptop queue")
    ap.add_argument("--sqs-dlq", default=None, help="SQS dead-letter queue URL (required with --sqs-queue)")
    ap.add_argument("--region", default="ap-south-1")
    ap.add_argument("--encoder", default="http://127.0.0.1:9000")
    ap.add_argument("--shards", default=os.environ.get("SHARD_URLS", DEFAULT_SHARDS))
    ap.add_argument("--drain", action="store_true", help="exit when the queue is empty (laptop queue only)")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--visibility", type=float, default=60.0)
    ap.add_argument("--max-receives", type=int, default=8)
    a = ap.parse_args()
    resolve = None
    if a.sqs_queue:
        import boto3

        from genkart.sqs_queue import SqsJobQueue
        if not a.sqs_dlq:
            ap.error("--sqs-dlq is required with --sqs-queue")
        queue = SqsJobQueue(boto3.client("sqs", region_name=a.region), a.sqs_queue, a.sqs_dlq)   # max receives is set on the SQS queue itself (redrive policy)
        resolve = S3Photos(boto3.client("s3", region_name=a.region))
    else:
        queue = JobQueue(a.queue, max_depth=10**6, max_receives=a.max_receives)
    w = IngestWorker(queue, a.encoder, parse_groups(a.shards), a.batch, a.visibility, resolve_image=resolve)
    try:
        w.run(a.drain)
    finally:
        print(json.dumps({"worker": "done", **w.stats}), flush=True)
