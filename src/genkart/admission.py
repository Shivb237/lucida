"""A gate in front of slow work: at most `concurrency` jobs run at once, the rest wait, and a waiting job LEAVES the queue the moment its deadline passes.

Why: the encoder used to start every request at once, so under overload they all shared the CPU and all finished late, after the router had already
given up on them (a 5 s limit). The encoder then kept computing answers nobody was waiting for, and stayed saturated after the load had stopped.
With the gate, a request whose caller has gone is dropped instead of computed. concurrency 0 disables the gate (the old behaviour, kept for measuring).
The deadline is an absolute time in milliseconds since 1970 (header x-deadline-ms); router and encoder run on the same machine, so their clocks agree.
"""
from __future__ import annotations

import threading
import time


class DeadlinePassed(Exception):
    pass


class Gate:
    def __init__(self, concurrency: int, clock=time.time):
        self._sem = threading.Semaphore(concurrency) if concurrency > 0 else None
        self._clock = clock
        self._lock = threading.Lock()
        self.stats = {"ran": 0, "dropped": 0}

    def run(self, fn, deadline_ms: float | None = None):
        if self._sem is None:
            return fn()
        wait = None if deadline_ms is None else max(0.0, deadline_ms / 1000 - self._clock())
        if not self._sem.acquire(timeout=wait):          # still no free slot when the deadline arrived: leave the queue
            self._drop()
        try:
            if deadline_ms is not None and self._clock() * 1000 > deadline_ms:   # a slot opened at the last moment, too late to be useful
                self._drop()
            result = fn()
            with self._lock:
                self.stats["ran"] += 1
            return result
        finally:
            self._sem.release()

    def _drop(self):
        with self._lock:
            self.stats["dropped"] += 1
        raise DeadlinePassed("the caller's deadline passed before this could run")
