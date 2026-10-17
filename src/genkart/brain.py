"""Bring your own model: understand the request with the visitor's own API key instead of the local model.

The key is held for the length of ONE request, in memory. It is never written to disk, never logged, never put in a step payload or a recorded run,
and is removed from any error text before the error is shown. It is sent only to the provider the visitor chose. The model's answer goes through
the same checks as the local model's (`understand.ground` and `qualify`), so a stronger model does not get to skip them.
Limits: a call count per server start (GENKART_BYO_MAX_CALLS, default 100), 600 output tokens per call, no retries (a failed call is not paid twice).
Two kinds: "anthropic" (the Messages API through the installed SDK, forced tool call) and "openai" (any server that speaks /chat/completions with JSON mode:
OpenAI, Groq, Together, a local vLLM or Ollama /v1 ...).
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.parse
from dataclasses import dataclass, field

import httpx

from genkart.understand import Plan

_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")
DEFAULTS = {"anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini"}
OPENAI_BASE = "https://api.openai.com/v1"
MAX_TOKENS = 600


class BrainError(Exception):
    """A problem with the visitor's own model settings or call. The message never contains the key."""


@dataclass(frozen=True)
class Brain:
    kind: str
    model: str
    key: str = field(repr=False)             # repr=False: the key must not show up in a log line or a traceback of this object
    base_url: str = ""

    def label(self) -> str:
        return f"{self.model} (your {'Anthropic' if self.kind == 'anthropic' else 'provider'} key)"


def scrub(text: str, key: str) -> str:
    """Remove the key (and its tail, which providers sometimes echo) from any text that is about to be shown or logged."""
    out = text.replace(key, "[key]") if key else text
    return out.replace(key[-6:], "[key]") if len(key) >= 12 else out


# Hosts a visitor may point "openai" mode at: the providers the web page lists. Anything else (a local vLLM, a company gateway) must be added by the
# person running the server with GENKART_BYO_HOSTS="host1,host2". An open list would let a visitor make THIS server call any address (SSRF).
KNOWN_HOSTS = frozenset({"api.openai.com", "generativelanguage.googleapis.com", "api.deepseek.com", "api.groq.com", "api.mistral.ai",
                         "openrouter.ai", "api.together.xyz"})


def _check_url(url: str) -> str:
    p = urllib.parse.urlparse(url)
    allowed = KNOWN_HOSTS | {h.strip().lower() for h in os.environ.get("GENKART_BYO_HOSTS", "").split(",") if h.strip()}
    try:
        host, port = p.hostname, p.port
    except ValueError:
        raise BrainError("the base address is not valid") from None
    if p.scheme != "https" or not host or p.username or p.password or p.query or p.fragment or port not in (None, 443):
        raise BrainError("the base address must be https://host/path with no login, port, ? or #")
    if host.lower() not in allowed:
        raise BrainError("that provider is not on this server's list (GENKART_BYO_HOSTS adds more)")
    return url.rstrip("/")


def parse(raw: dict) -> Brain:
    """Validate what the page sent. Raises BrainError with a plain message (never containing the key)."""
    kind = str(raw.get("kind", ""))
    if kind not in DEFAULTS:
        raise BrainError("kind must be anthropic or openai")
    key = str(raw.get("key", "")).strip()
    if not 8 <= len(key) <= 400 or re.search(r"\s", key):
        raise BrainError("the key looks wrong (8 to 400 characters, no spaces)")
    model = str(raw.get("model") or DEFAULTS[kind]).strip()
    if not _MODEL.match(model):
        raise BrainError("the model name has characters a model name does not have")
    base = ""
    if kind == "openai":
        base = _check_url(str(raw.get("base_url") or OPENAI_BASE))
    return Brain(kind, model, key, base)


_calls = 0
_lock = threading.Lock()


def _count_call() -> None:
    global _calls
    limit = int(os.environ.get("GENKART_BYO_MAX_CALLS", "100"))
    with _lock:
        if limit and _calls >= limit:      # 0 = off (the hosted Lab: the keys are the visitors' own, and one visitor must not use up everyone's calls)
            raise BrainError(f"this server has already made {limit} calls with a key since it started (the limit protects your account); restart it to continue")
        _calls += 1


def _json_object(text: str) -> dict:
    """The model's answer as JSON. Many models wrap it in a code fence or add a sentence around it: take the first {...} block."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            raise BrainError("the model did not answer with JSON") from None
        return json.loads(m.group(0))


class BrainChain:
    """Same shape as the LangChain chain `understand()` expects: .invoke({'system', 'request'}) -> Plan."""

    def __init__(self, brain: Brain, client: httpx.Client | None = None):
        self.brain, self.http = brain, client or httpx.Client(timeout=httpx.Timeout(60.0, connect=5.0))
        self._own_http = client is None
        self.usage: dict | None = None      # tokens the provider billed for the last call: {input_tokens, output_tokens}

    def invoke(self, args: dict) -> Plan:
        _count_call()
        try:
            return self._ask_anthropic(args) if self.brain.kind == "anthropic" else self._ask_openai(args)
        except BrainError:
            raise
        except Exception as e:  # noqa: BLE001  whatever the provider or network did, the key must not leave inside the message
            raise BrainError(scrub(f"{type(e).__name__}: {e}", self.brain.key)[:400]) from None
        finally:
            if self._own_http:
                self.http.close()

    def _ask_anthropic(self, args: dict) -> Plan:
        from anthropic import Anthropic

        client = Anthropic(api_key=self.brain.key, max_retries=0, timeout=60.0)
        tool = {"name": "answer", "description": "Return the product search plan.", "input_schema": Plan.model_json_schema()}
        resp = client.messages.create(model=self.brain.model, max_tokens=MAX_TOKENS, system=args["system"], messages=[{"role": "user", "content": f"Request: {args['request']}"}],
                                      tools=[tool], tool_choice={"type": "tool", "name": "answer"})
        self.usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens} if getattr(resp, "usage", None) else None
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None:
            raise BrainError("the model did not answer with a plan")
        return Plan.model_validate(block.input)

    def _ask_openai(self, args: dict) -> Plan:
        schema = json.dumps(Plan.model_json_schema())
        body = {"model": self.brain.model, "temperature": 0, "max_tokens": MAX_TOKENS, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": args["system"] + "\nAnswer with ONE JSON object that matches this JSON schema: " + schema},
                             {"role": "user", "content": f"Request: {args['request']}"}]}
        url, headers = f"{self.brain.base_url}/chat/completions", {"authorization": f"Bearer {self.brain.key}"}
        r = self.http.post(url, json=body, headers=headers)
        if r.status_code == 400:           # some providers do not know JSON mode: the prompt already demands JSON only, so ask again without it
            body.pop("response_format")
            r = self.http.post(url, json=body, headers=headers)
        if r.status_code == 401:
            raise BrainError("the provider refused the key (401)")
        if r.status_code == 429:
            raise BrainError("the provider says too many requests (429): wait a moment or check your plan")
        r.raise_for_status()
        data = r.json()
        u = data.get("usage") or {}
        self.usage = {"input_tokens": u["prompt_tokens"], "output_tokens": u["completion_tokens"]} if "prompt_tokens" in u else None
        return Plan.model_validate(_json_object(data["choices"][0]["message"]["content"]))
