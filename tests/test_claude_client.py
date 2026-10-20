"""The Claude spend caps: per purpose, and one total over every purpose that no script can pass."""
import json

import pytest

from genkart.claude_client import TOTAL_CAP_USD, CapExceeded, CappedClaude, ledger_total


def _client(tmp_path, rows, purpose="plans", cap=5.0):
    ledger = tmp_path / "spend.jsonl"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    c = CappedClaude.__new__(CappedClaude)               # no API key, no network: the cap check must refuse before any call is made
    c.client, c.model, c.cap, c.purpose, c.pin, c.pout, c.ledger, c.spent, c.calls = None, "claude-sonnet-5-5", cap, purpose, 2.0, 10.0, ledger, 0.0, 0
    return c


def test_ledger_total_adds_every_purpose(tmp_path):
    c = _client(tmp_path, [{"purpose": "a", "cost_usd": 1.25}, {"purpose": "b", "cost_usd": 0.5}])
    assert ledger_total(c.ledger) == pytest.approx(1.75)
    assert ledger_total(tmp_path / "missing.jsonl") == 0.0


def test_a_purpose_with_room_is_still_refused_when_all_purposes_together_would_pass_the_total(tmp_path):
    c = _client(tmp_path, [{"purpose": "judge", "cost_usd": TOTAL_CAP_USD - 0.01}], purpose="plans", cap=5.0)
    with pytest.raises(CapExceeded, match="total budget"):
        c.call("system", "hello", max_tokens=1000, est_input_tokens=100)    # worst case about $0.01: passes the purpose cap, not the total


def test_two_clients_sharing_a_ledger_cannot_both_pass_the_check_before_either_books(tmp_path):
    """Check, call and booking are one step under a file lock: with room for one call only, two racing callers make exactly one call."""
    import threading
    import time

    calls = []

    class Slow:
        def create(self, **kw):
            calls.append(1)
            time.sleep(0.2)                  # both threads are inside call() at the same time
            return type("R", (), {"usage": type("U", (), {"input_tokens": 1000, "output_tokens": 1000})})

    rows = [{"purpose": "other", "cost_usd": TOTAL_CAP_USD - 0.015}]           # room for one ~$0.012 call, not two
    a, b = _client(tmp_path, rows), _client(tmp_path, [])
    b.ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    for c in (a, b):
        c.client = type("C", (), {"messages": Slow()})()
    errors = []

    def go(c):
        try:
            c.call("s", "x", max_tokens=1000, est_input_tokens=1000)
        except CapExceeded as e:
            errors.append(e)

    ts = [threading.Thread(target=go, args=(c,)) for c in (a, b)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(calls) == 1 and len(errors) == 1
    assert ledger_total(a.ledger) <= TOTAL_CAP_USD
