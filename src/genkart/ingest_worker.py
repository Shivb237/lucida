"""Ingest worker: takes new-product messages from the job queue, embeds the photo, adds the product to EVERY replica of its shard.

A message is acknowledged only when every replica of the owning shard accepted it. Failures are of two kinds:
  permanent (the server says the request itself is wrong: a missing photo, an invalid id)  -> dead-letter queue at once
  transient (a replica or the encoder is unreachable, a timeout)                           -> retried later with exponential backoff
After max_receives tries a message lands in the dead-letter queue anyway; redrive() (JobQueue or SqsJobQueue) replays it once the cause is fixed.
Adding is idempotent on the shard side, so retries and duplicates are harmless.
A replica that is unreachable or answers 503 pauses the worker: it stops receiving (which would only burn the messages' retry budget) and asks the
replica's /health on every step until it answers, then carries on. Products for one shard are sent in batches of up to WRITE_BATCH per request.
A photo fetched from S3 is deleted once it has been embedded (the worker's disk holds only the photos of the batch in hand).
GENKART_SHARD_TOKEN, when set, is sent as the x-genkart-token header on every /ingest (the shard refuses an ingest without it).
Run on a laptop:  PYTHONPATH=src .venv/bin/python -m genkart.ingest_worker --queue data/ingest/queue.db [--drain]
Run on AWS:       python -m genkart.ingest_worker --sqs-queue URL --sqs-dlq URL --region ap-south-1   (shards from $SHARD_URLS; photos named s3://... are fetched first)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import pathlib
import time
import traceback

import httpx

from genkart.jobqueue import JobQueue

WRITE_BATCH = 32
ITEM_ERRORS = (400, 404, 409, 413, 422)   # answers that blame the items sent, not the replica
log = logging.getLogger("genkart.ingest")
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

    def cleanup(self, image: str) -> None:
        """Delete the local copy of an S3 photo (a local path given by the producer is never touched)."""
        if image.startswith("s3://"):
            bucket, _, key = image[5:].partition("/")
            (self.dir / (hashlib.sha256(image.encode()).hexdigest()[:24] + pathlib.PurePosixPath(key).suffix)).unlink(missing_ok=True)


def backoff_s(receive_count: int, base: float = 2.0, cap: float = 60.0) -> float:
    return min(cap, base * 2 ** max(0, receive_count - 1))


def parse_groups(spec: str) -> list[list[str]]:
    return [[u.strip() for u in g.split("|") if u.strip()] for g in spec.split(",") if g.strip()]


class IngestWorker:
    def __init__(self, queue: JobQueue, encoder_url: str, groups: list[list[str]], batch: int = 8, visibility_s: float = 60.0, timeout_s: float = 10.0, client: httpx.Client | None = None, resolve_image=None,
                 write_batch: int = WRITE_BATCH, token: str | None = None):
        self.queue, self.encoder_url, self.groups, self.batch, self.visibility_s = queue, encoder_url, groups, batch, visibility_s
        self.resolve_image = resolve_image or (lambda image: image)
        self.http = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=2.0))   # a switched-off computer never answers: notice in 2 s, not 10 s
        self.write_batch = max(1, write_batch)
        token = os.environ.get("GENKART_SHARD_TOKEN", "") if token is None else token
        self.headers = {"x-genkart-token": token} if token else {}
        self.down: set[str] = set()                 # replicas unreachable, refusing our token, or failing as a whole: nothing is received until they are back
        self.stats = {"acked": 0, "failed_attempts": 0, "batches": 0}

    def _embed(self, paths: list[str]) -> list[list[float]]:
        r = self.http.post(f"{self.encoder_url}/encode_images", json={"paths": [self.resolve_image(p) for p in paths]})
        r.raise_for_status()
        return r.json()["vectors"]

    def _post(self, url: str, items: list[dict]) -> str | None:
        """One /ingest call; None when accepted, else the error text. Only an answer about the items (400, 404, 409, 413, 422) is the items' fault.
        Anything else (no answer, 401/403 = wrong or missing token, 5xx) is the replica's: it is marked down, so the queue pauses instead of
        spending every message's retries on a replica that cannot take any of them."""
        try:
            r = self.http.post(f"{url}/ingest", json={"items": items}, headers=self.headers)
            r.raise_for_status()
            return None
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, httpx.HTTPStatusError) or e.response.status_code not in ITEM_ERRORS:
                self.down.add(url)
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                    log.error("replica %s refused the shard token (HTTP %s): check GENKART_SHARD_TOKEN on both sides", url, e.response.status_code)
            return f"{url}: {e}"

    def _write_many(self, items: list[dict]) -> dict[str, str]:
        """Add items to every replica of their shard, up to write_batch per request. Returns {id: error} for the items NOT on every replica."""
        errors: dict[str, list[str]] = {}
        by_group: dict[int, list[dict]] = {}
        for it in items:
            by_group.setdefault(int(it["id"]) % len(self.groups), []).append(it)
        for g, its in by_group.items():
            for i in range(0, len(its), self.write_batch):
                chunk = its[i:i + self.write_batch]
                for url in self.groups[g]:
                    err = self._post(url, chunk)
                    if err and len(chunk) > 1 and url not in self.down:      # refused (422 ...): send one by one so only the bad item fails
                        for it in chunk:
                            e1 = self._post(url, [it])
                            if e1:
                                errors.setdefault(it["id"], []).append(e1)
                    elif err:
                        for it in chunk:
                            errors.setdefault(it["id"], []).append(err)
        return {k: "; ".join(v) for k, v in errors.items()}

    def _write(self, item: dict) -> None:
        """Add one item to every replica of its shard; raises unless all of them accepted it."""
        err = self._write_many([item]).get(item["id"])
        if err:
            raise RuntimeError(err)

    def _replicas_back(self) -> bool:
        """Ask each replica marked down with an empty /ingest (it adds nothing, but checks the token too, which /health does not); True when none is down."""
        for url in sorted(self.down):
            try:
                if self.http.post(f"{url}/ingest", json={"items": []}, headers=self.headers).status_code == 200:
                    self.down.discard(url)
            except Exception:  # noqa: BLE001  still unreachable
                pass
        return not self.down

    def step(self) -> int:
        """Handle one batch. Returns the number of messages received (0 = the queue is empty, everything is in flight, or a replica is down)."""
        if self.down and not self._replicas_back():
            self.stats["paused"] = self.stats.get("paused", 0) + 1
            return 0
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
        cleanup = getattr(self.resolve_image, "cleanup", None)
        if cleanup:                                     # embedded (or failed): the downloaded photo is not needed any more
            for m in msgs:
                try:
                    cleanup(m["body"]["image"])
                except Exception:  # noqa: BLE001  a photo that cannot be deleted must not stop the batch
                    pass
        ready = [m for m in msgs if m["receipt"] in vectors]
        self.stats["failed_attempts"] += len(msgs) - len(ready)
        for i in range(0, len(ready), self.write_batch):
            if late():                                  # too slow to finish these safely: leave them, they reappear in a moment
                self.stats["skipped_late"] = self.stats.get("skipped_late", 0) + len(ready) - i
                break
            chunk = ready[i:i + self.write_batch]
            try:
                errors = self._write_many([{"id": m["body"]["id"], "vector": vectors[m["receipt"]], "source": m["body"]["source"], "gender": m["body"].get("gender", ""),
                                            "cluster": m["body"]["cluster"], "title": m["body"]["title"]} for m in chunk])
            except Exception as e:  # noqa: BLE001  a malformed body (a missing field) fails its whole chunk, never the worker
                errors = {m["body"].get("id"): f"{type(e).__name__}: {e}" for m in chunk}
            for m in chunk:
                err = errors.get(m["body"].get("id"))
                if err:
                    self.queue.fail(m["receipt"], f"write: {err}", backoff_s(m["receive_count"]))
                    self.stats["failed_attempts"] += 1
                elif self.queue.delete(m["receipt"]):
                    self.stats["acked"] += 1
                else:                                   # written to every replica but the acknowledgement was refused: it will be handled again (harmless, adding is idempotent)
                    self.stats["delete_failed"] = self.stats.get("delete_failed", 0) + 1
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
            idle += 1
            if self.down:                               # paused: a replica is down. Look again in a few seconds, without receiving anything
                if drain and idle > max_idle_cycles:
                    return
                time.sleep(max(idle_s, 2.0))
                continue
            if drain:
                s = self.queue.stats()
                if s["waiting"] == 0 and s["in_flight"] == 0:
                    return
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
