"""The encoder's gate: at most N jobs at once, and a waiting job whose deadline passed is dropped, never run."""
import threading
import time

import pytest

from genkart.admission import DeadlinePassed, Gate


def test_disabled_gate_just_runs_the_job():
    assert Gate(0).run(lambda: 42) == 42


def test_at_most_n_jobs_run_at_once():
    gate, running, peak, lock = Gate(2), [0], [0], threading.Lock()

    def job():
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1

    threads = [threading.Thread(target=gate.run, args=(job,)) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 2 and gate.stats["ran"] == 8


def test_a_waiting_job_leaves_the_queue_when_its_deadline_passes_and_never_runs():
    gate, ran = Gate(1), []
    started = threading.Event()
    blocker = threading.Thread(target=gate.run, args=(lambda: (started.set(), time.sleep(0.3)),))
    blocker.start()
    started.wait()
    soon = time.time() * 1000 + 50                                  # this caller stops waiting in 50 ms
    t0 = time.time()
    with pytest.raises(DeadlinePassed):
        gate.run(lambda: ran.append(1), deadline_ms=soon)
    assert time.time() - t0 < 0.2 and ran == []                     # it left at about 50 ms, long before the blocker finished
    blocker.join()
    assert gate.stats["dropped"] == 1


def test_a_deadline_that_is_already_past_drops_even_when_the_gate_is_free():
    gate = Gate(2)
    with pytest.raises(DeadlinePassed):
        gate.run(lambda: 1, deadline_ms=time.time() * 1000 - 1000)
    assert gate.run(lambda: 1, deadline_ms=time.time() * 1000 + 5000) == 1     # a deadline in the future runs normally


def test_a_failing_job_still_frees_its_slot():
    gate = Gate(1)
    with pytest.raises(RuntimeError):
        gate.run(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert gate.run(lambda: "next job runs") == "next job runs"
