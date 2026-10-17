"""Claude API client with a HARD spend cap, for small paid checks only. The key comes from .env (ANTHROPIC_API_KEY), never printed or logged.

Before every call we reserve the worst case (input tokens estimated from the text, plus the full max_tokens of output) and refuse to call
if spent + reserve would pass the cap. After the call the real token counts from the API response are booked. Every call is appended to a
ledger file so the total can be audited. Prices are per million tokens (USD), from https://platform.claude.com/docs/en/about-claude/pricing
read 2026-10-14; update them here if they change.
"""
from __future__ import annotations

import json
import os
import pathlib
import time

PRICES = {  # (input, output) USD per million tokens
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),   # prompts up to 100,000 tokens
}


TOTAL_CAP_USD = 5.64   # the whole project's Claude budget (the project's budget note): no purpose, and no two scripts running together, can push the grand total past it


class CapExceeded(RuntimeError):
    pass


def ledger_total(path: pathlib.Path) -> float:
    """Everything every purpose has spent, read fresh from the ledger file."""
    p = pathlib.Path(path)
    return sum(json.loads(l).get("cost_usd", 0.0) for l in p.open() if l.strip()) if p.exists() else 0.0


class CappedClaude:
    def __init__(self, model: str, cap_usd: float, ledger: str, purpose: str):
        from anthropic import Anthropic
        from dotenv import load_dotenv

        load_dotenv()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")
        self.client = Anthropic(max_retries=1, timeout=60.0)
        self.model, self.cap, self.purpose = model, cap_usd, purpose
        self.pin, self.pout = PRICES[model]
        self.ledger = pathlib.Path(ledger)
        self.spent, self.calls = 0.0, 0
        if self.ledger.exists():  # resume: count what earlier runs with this ledger already spent
            rows = [json.loads(l) for l in self.ledger.open() if l.strip()]
            self.spent = sum(r["cost_usd"] for r in rows if r["purpose"] == purpose)   # the cap is per purpose; the ledger keeps the grand total

    def _cost(self, tin: int, tout: int) -> float:
        return (tin * self.pin + tout * self.pout) / 1e6

    def call(self, system: str, content, max_tokens: int, tools=None, tool_choice=None, est_input_tokens: int | None = None, **extra):
        est_in = est_input_tokens if est_input_tokens is not None else (len(system) + len(json.dumps(content, default=str))) // 3 + 200
        worst = self._cost(est_in, max_tokens)
        if self.spent + worst > self.cap:
            raise CapExceeded(f"spent ${self.spent:.4f} + worst case ${worst:.4f} would pass the ${self.cap:.2f} cap")
        total = ledger_total(self.ledger)
        if total + worst > TOTAL_CAP_USD:
            raise CapExceeded(f"all purposes together have spent ${total:.4f}; with this call's worst case ${worst:.4f} that would pass the ${TOTAL_CAP_USD:.2f} total budget")
        kw = dict(model=self.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": content}])
        if tools:
            kw.update(tools=tools, tool_choice=tool_choice)
        kw.update(extra)
        t = time.time()
        resp = self.client.messages.create(**kw)
        cost = self._cost(resp.usage.input_tokens, resp.usage.output_tokens)
        self.spent += cost
        self.calls += 1
        with self.ledger.open("a") as f:
            f.write(json.dumps({"ts": round(time.time()), "purpose": self.purpose, "model": self.model, "input_tokens": resp.usage.input_tokens,
                                "output_tokens": resp.usage.output_tokens, "cost_usd": round(cost, 6), "seconds": round(time.time() - t, 2)}) + "\n")
        return resp
