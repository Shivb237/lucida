"""A small durable job queue with Amazon SQS semantics, backed by SQLite (survives restarts).

send()      adds a message; a dedup key makes sending the same thing twice within `dedup_window_s` a no-op, even after the first was acknowledged
            (idempotent producer); raises QueueFull at max_depth (backpressure)
receive()   hands out up to n visible messages and hides each for `visibility_s` seconds; every hand-out increments receive_count
delete()    acknowledges a message by its receipt handle: only then is it gone for good
fail()      records why a worker gave up and may delay the retry (backoff); dead_now() parks a message in the dead-letter queue at once (a permanent error)
a message received more than `max_receives` times without being deleted is moved to the dead-letter queue instead of being handed out again
redrive()   moves dead-lettered messages back into the queue (after the cause, such as a replica outage, is fixed)
Delivery is at least once: a worker that dies leaves its messages to reappear after the visibility timeout, so consumers must be idempotent.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid


class QueueFull(Exception):
    pass


class JobQueue:
    def __init__(self, path: str, max_depth: int = 1000, max_receives: int = 3, clock=time.time, dedup_window_s: float = 300.0):
        self.path, self.max_depth, self.max_receives, self.clock, self.dedup_window_s = path, max_depth, max_receives, clock, dedup_window_s
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=30, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, dedup TEXT, body TEXT NOT NULL, visible_at REAL NOT NULL,
            receive_count INTEGER NOT NULL DEFAULT 0, receipt TEXT, dead INTEGER NOT NULL DEFAULT 0, error TEXT)""")
        self._db.execute("CREATE TABLE IF NOT EXISTS seen (dedup TEXT PRIMARY KEY, at REAL NOT NULL)")

    def send(self, body: dict, dedup: str | None = None) -> bool:
        """True when the message was added, False when its dedup key was already known (a retry of the producer)."""
        with self._lock:
            now = self.clock()
            depth = self._db.execute("SELECT COUNT(*) FROM messages WHERE dead = 0").fetchone()[0]
            if dedup is not None:
                row = self._db.execute("SELECT at FROM seen WHERE dedup = ?", (dedup,)).fetchone()
                if row and now - row[0] < self.dedup_window_s:
                    return False
            if depth >= self.max_depth:
                raise QueueFull(f"queue holds {depth} messages (max {self.max_depth})")
            self._db.execute("INSERT INTO messages (dedup, body, visible_at) VALUES (?, ?, ?)", (dedup, json.dumps(body), now))
            if dedup is not None:
                self._db.execute("INSERT OR REPLACE INTO seen (dedup, at) VALUES (?, ?)", (dedup, now))
            return True

    def receive(self, n: int = 10, visibility_s: float = 30.0) -> list[dict]:
        now = self.clock()
        out = []
        with self._lock:
            rows = self._db.execute("SELECT id, body, receive_count FROM messages WHERE dead = 0 AND visible_at <= ? ORDER BY id LIMIT ?", (now, n * 3)).fetchall()
            for mid, body, count in rows:
                if len(out) == n:
                    break
                if count >= self.max_receives:      # tried enough times: park it in the dead-letter queue
                    self._db.execute("UPDATE messages SET dead = 1, receipt = NULL WHERE id = ?", (mid,))
                    continue
                receipt = uuid.uuid4().hex
                self._db.execute("UPDATE messages SET receive_count = receive_count + 1, visible_at = ?, receipt = ? WHERE id = ?", (now + visibility_s, receipt, mid))
                out.append({"receipt": receipt, "body": json.loads(body), "receive_count": count + 1})
        return out

    def delete(self, receipt: str) -> bool:
        with self._lock:
            return self._db.execute("DELETE FROM messages WHERE receipt = ?", (receipt,)).rowcount > 0

    def fail(self, receipt: str, error: str, retry_after_s: float = 0.0) -> None:
        """Record why a worker gave up. The message stays and reappears after its visibility timeout, or after retry_after_s when given (backoff)."""
        with self._lock:
            if retry_after_s > 0:
                self._db.execute("UPDATE messages SET error = ?, visible_at = ? WHERE receipt = ?", (error[:300], self.clock() + retry_after_s, receipt))
            else:
                self._db.execute("UPDATE messages SET error = ? WHERE receipt = ?", (error[:300], receipt))

    def dead_now(self, receipt: str, error: str) -> None:
        """A permanent error (a missing photo, an invalid id): retrying cannot help, so park the message in the dead-letter queue at once."""
        with self._lock:
            self._db.execute("UPDATE messages SET dead = 1, error = ?, receipt = NULL WHERE receipt = ?", (error[:300], receipt))

    def redrive(self, error_prefix: str | None = None) -> int:
        """Move dead-lettered messages (optionally only those whose error starts with a prefix) back into the queue with a fresh retry budget."""
        with self._lock:
            now = self.clock()
            if error_prefix is None:
                return self._db.execute("UPDATE messages SET dead = 0, receive_count = 0, visible_at = ?, receipt = NULL WHERE dead = 1", (now,)).rowcount
            return self._db.execute("UPDATE messages SET dead = 0, receive_count = 0, visible_at = ?, receipt = NULL WHERE dead = 1 AND error LIKE ?",
                                    (now, error_prefix + "%")).rowcount

    def dead_letters(self) -> list[dict]:
        with self._lock:
            return [{"id": i, "body": json.loads(b), "receive_count": c, "error": e}
                    for i, b, c, e in self._db.execute("SELECT id, body, receive_count, error FROM messages WHERE dead = 1")]

    def stats(self) -> dict:
        now = self.clock()
        with self._lock:
            q = lambda sql, *a: self._db.execute(sql, a).fetchone()[0]  # noqa: E731
            return {"waiting": q("SELECT COUNT(*) FROM messages WHERE dead = 0 AND visible_at <= ?", now),
                    "in_flight": q("SELECT COUNT(*) FROM messages WHERE dead = 0 AND visible_at > ?", now),
                    "dead": q("SELECT COUNT(*) FROM messages WHERE dead = 1"), "max_depth": self.max_depth}
