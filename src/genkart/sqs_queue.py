"""The same queue calls as genkart.jobqueue.JobQueue, on Amazon SQS (FIFO queue + its dead-letter queue). IngestWorker works with either.

What maps directly: receive (ReceiveMessage), delete (DeleteMessage), fail with a delay (ChangeMessageVisibility), send (SendMessage).
What differs from the laptop queue, on purpose and written down:
- Duplicates: SQS FIFO drops a repeat of the same MessageDeduplicationId within 5 minutes (fixed by AWS) and still returns success, so send() cannot tell
  "added" from "dropped as a duplicate"; it returns True either way.
- Backpressure: SQS has no maximum depth. send() checks the (approximate, up to about a minute stale) queue size itself and raises QueueFull.
- dead_now(): SQS cannot move one message to the dead-letter queue on demand. We send a copy to the DLQ with the error text attached, then delete the
  original. If the process dies between the two, the original reappears and is retried (harmless: the shard side is idempotent).
- Errors: SQS keeps no error text for a failed attempt, so fail() logs it. Only dead_now() preserves the error (as a message attribute in the DLQ).
- Every message is its own FIFO "message group" (the product id), so one stuck message never blocks the others; order does not matter because adding is idempotent.
- stats() are approximate (SQS counts lag), so the worker's --drain mode is not reliable on SQS; run the worker as a service instead.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from genkart.jobqueue import QueueFull

log = logging.getLogger("genkart.sqs")


class SqsJobQueue:
    def __init__(self, client, queue_url: str, dlq_url: str, max_depth: int = 10**6, wait_s: int = 5, clock=time.time):
        """client: a boto3 SQS client (any object with the same methods works, which is how the tests run without AWS)."""
        self.sqs, self.url, self.dlq_url, self.max_depth, self.wait_s, self.clock = client, queue_url, dlq_url, max_depth, wait_s, clock
        self._bodies: dict[str, tuple[str, str]] = {}   # receipt -> (raw body, group id), needed by dead_now() to copy the message to the DLQ
        self._depth_at, self._depth = 0.0, 0

    def _approx(self, url: str, name: str) -> int:
        return int(self.sqs.get_queue_attributes(QueueUrl=url, AttributeNames=[name])["Attributes"][name])

    def send(self, body: dict, dedup: str | None = None) -> bool:
        now = self.clock()
        if now - self._depth_at > 5:                    # at most one size check per 5 seconds
            self._depth, self._depth_at = self._approx(self.url, "ApproximateNumberOfMessages"), now
        if self._depth >= self.max_depth:
            raise QueueFull(f"queue holds about {self._depth} messages (max {self.max_depth})")
        key = dedup if dedup is not None else uuid.uuid4().hex
        self.sqs.send_message(QueueUrl=self.url, MessageBody=json.dumps(body), MessageGroupId=key[:128], MessageDeduplicationId=key[:128])
        return True

    def _remember(self, receipt: str, body: str, group: str) -> None:
        self._bodies[receipt] = (body, group)
        if len(self._bodies) > 2000:             # receipts of skipped or abandoned messages are never used again: without this the dict grows for ever
            for old_receipt in list(self._bodies)[:1000]:
                del self._bodies[old_receipt]

    def receive(self, n: int = 10, visibility_s: float = 30.0) -> list[dict]:
        resp = self.sqs.receive_message(QueueUrl=self.url, MaxNumberOfMessages=max(1, min(n, 10)), VisibilityTimeout=int(visibility_s),
                                        WaitTimeSeconds=self.wait_s, MessageSystemAttributeNames=["ApproximateReceiveCount", "MessageGroupId"])
        out = []
        for m in resp.get("Messages", []):
            receipt = m["ReceiptHandle"]
            self._remember(receipt, m["Body"], m.get("Attributes", {}).get("MessageGroupId", uuid.uuid4().hex))
            try:
                body = json.loads(m["Body"])
            except ValueError:                    # not JSON: retrying cannot help, and it must not hold up the messages received with it
                self.dead_now(receipt, "unreadable message body (not JSON)")
                continue
            out.append({"receipt": receipt, "body": body, "receive_count": int(m.get("Attributes", {}).get("ApproximateReceiveCount", "1"))})
        return out

    def delete(self, receipt: str) -> bool:
        try:
            self.sqs.delete_message(QueueUrl=self.url, ReceiptHandle=receipt)
        except Exception as e:  # noqa: BLE001  an expired or invalid receipt means someone else owns the message now
            log.warning("delete failed: %s", e)
            return False
        self._bodies.pop(receipt, None)
        return True

    def fail(self, receipt: str, error: str, retry_after_s: float = 0.0) -> None:
        log.warning("attempt failed (will retry): %s", error[:300])
        self._bodies.pop(receipt, None)           # a failed attempt is over; the message will come back with a new receipt
        if retry_after_s > 0:
            try:
                self.sqs.change_message_visibility(QueueUrl=self.url, ReceiptHandle=receipt, VisibilityTimeout=int(min(retry_after_s, 43200)))
            except Exception as e:  # noqa: BLE001  the hiding time already ran out (the message is visible again, maybe held by someone else): it will be retried anyway
                log.warning("could not change the retry delay (the message reappears on its own): %s", str(e)[:200])

    def dead_now(self, receipt: str, error: str) -> None:
        body, group = self._bodies.get(receipt, (None, None))
        if body is None:
            raise KeyError("unknown receipt: dead_now needs a message received by this process")
        self.sqs.send_message(QueueUrl=self.dlq_url, MessageBody=body, MessageGroupId=group[:128], MessageDeduplicationId=uuid.uuid4().hex,
                              MessageAttributes={"error": {"DataType": "String", "StringValue": error[:1000]}})
        self.delete(receipt)

    def stats(self) -> dict:
        a = self.sqs.get_queue_attributes(QueueUrl=self.url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
        return {"waiting": int(a["ApproximateNumberOfMessages"]), "in_flight": int(a["ApproximateNumberOfMessagesNotVisible"]),
                "dead": self._approx(self.dlq_url, "ApproximateNumberOfMessages"), "max_depth": self.max_depth, "approximate": True}
