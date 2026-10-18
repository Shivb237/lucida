"""Bring your own model: the visitor's key is validated, used for one request, and must never appear in an event, an error, a repr or a response."""
import http.server
import json
import threading

import pytest
from fastapi.testclient import TestClient

from genkart import brain as brain_mod
from genkart.brain import Brain, BrainChain, BrainError, parse, scrub
from genkart.server import Services, create_app, run_pipeline
from genkart.understand import Piece, Plan
from test_server import make_services

KEY = "sk-test-SECRET-1234567890abcdef"
PLAN = {"main_query": "men's red kurta", "gender": "men", "pieces": [{"kind": "top", "search_text": "men's red kurta", "colours": ["red"]}]}


def _provider(status=200, body=None, echo_key=False, content=None, reject_json_mode=False):
    seen = {"calls": 0}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers["content-length"]))
            seen["auth"], seen["path"], seen["body"] = self.headers.get("authorization"), self.path, json.loads(raw)
            seen["calls"] += 1
            code = 400 if reject_json_mode and "response_format" in seen["body"] else status
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.end_headers()
            payload = body if body is not None else {"choices": [{"message": {"content": content if content is not None else json.dumps(PLAN)}}]}
            if echo_key:
                payload = {"error": f"bad key {KEY}"}
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


@pytest.fixture(autouse=True)
def fresh_counter(monkeypatch):
    monkeypatch.setattr(brain_mod, "_calls", 0)


def test_parse_accepts_good_settings_and_fills_defaults():
    b = parse({"kind": "anthropic", "key": KEY})
    assert b.model == "claude-haiku-5-5" and b.base_url == ""
    o = parse({"kind": "openai", "key": KEY, "base_url": "https://api.groq.com/openai/v1/"})
    assert o.base_url == "https://api.groq.com/openai/v1"


@pytest.mark.parametrize("raw", [
    {"kind": "nope", "key": KEY}, {"kind": "openai", "key": "short"}, {"kind": "openai", "key": "has a space in it 12345"},
    {"kind": "openai", "key": KEY, "model": "bad model!"}, {"kind": "openai", "key": KEY, "base_url": "ftp://x"},
    {"kind": "openai", "key": KEY, "base_url": "http://169.254.169.254/latest"},
    # the ways a visitor could aim this server at itself or its network (SSRF): each must be refused
    *[{"kind": "openai", "key": KEY, "base_url": u} for u in (
        "http://127.0.0.1:9100/", "https://localhost/v1", "https://10.0.0.5/v1", "https://[::1]/v1", "https://2852039166/", "https://0x7f000001/",
        "https://api.groq.com@evil.example/v1", "https://api.groq.com.evil.example/v1", "https://api.groq.com:8443/v1",
        "https://api.groq.com/v1?x=1", "https://api.groq.com/v1#x", "https://evil.example/v1")],
])
def test_parse_refuses_bad_settings_without_echoing_the_key(raw):
    with pytest.raises(BrainError) as e:
        parse(raw)
    assert KEY not in str(e.value)


def test_the_key_is_not_in_the_repr_and_scrub_removes_it_and_its_tail():
    b = Brain("openai", "m", KEY, "https://x")
    assert KEY not in repr(b) and "SECRET" not in repr(b)
    assert KEY not in scrub(f"failed with {KEY}", KEY) and KEY[-6:] not in scrub(f"...{KEY[-6:]}", KEY)


def test_openai_compatible_call_sends_the_key_only_as_the_bearer_header_and_returns_a_plan():
    srv, seen = _provider()
    try:
        chain = BrainChain(Brain("openai", "m1", KEY, f"http://127.0.0.1:{srv.server_port}/v1"))
        plan = chain.invoke({"system": "SYS", "request": "red kurta"})
        assert plan.pieces[0].search_text == "men's red kurta"
        assert seen["auth"] == f"Bearer {KEY}" and seen["path"] == "/v1/chat/completions"
        assert KEY not in json.dumps(seen["body"])                 # never inside the message body
        assert seen["body"]["max_tokens"] == 600 and seen["body"]["temperature"] == 0
    finally:
        srv.shutdown()


@pytest.mark.parametrize("status,words", [(401, "refused the key"), (429, "too many requests")])
def test_provider_errors_become_plain_messages(status, words):
    srv, _ = _provider(status=status, body={"error": "x"})
    try:
        with pytest.raises(BrainError, match=words):
            BrainChain(Brain("openai", "m", KEY, f"http://127.0.0.1:{srv.server_port}/v1")).invoke({"system": "s", "request": "r"})
    finally:
        srv.shutdown()


def test_a_provider_that_echoes_the_key_in_its_error_does_not_leak_it():
    srv, _ = _provider(status=500, echo_key=True)
    try:
        with pytest.raises(BrainError) as e:
            BrainChain(Brain("openai", "m", KEY, f"http://127.0.0.1:{srv.server_port}/v1")).invoke({"system": "s", "request": "r"})
        assert KEY not in str(e.value)
    finally:
        srv.shutdown()


def test_the_call_limit_stops_runaway_use(monkeypatch):
    monkeypatch.setenv("GENKART_BYO_MAX_CALLS", "1")
    srv, _ = _provider()
    try:
        chain = BrainChain(Brain("openai", "m", KEY, f"http://127.0.0.1:{srv.server_port}/v1"))
        chain.invoke({"system": "s", "request": "r"})
        with pytest.raises(BrainError, match="already made 1 calls"):
            chain.invoke({"system": "s", "request": "r"})
    finally:
        srv.shutdown()


def test_a_limit_of_zero_means_no_call_limit(monkeypatch):
    monkeypatch.setenv("GENKART_BYO_MAX_CALLS", "0")
    srv, _ = _provider()
    try:
        for _ in range(3):      # a new chain per request, as the server does
            BrainChain(Brain("openai", "m", KEY, f"http://127.0.0.1:{srv.server_port}/v1")).invoke({"system": "s", "request": "r"})
    finally:
        srv.shutdown()


def _services(understand_byo):
    base = make_services()
    return Services(base.ollama_up, base.understand, base.expand, base.search, base.colour, base.health, None, understand_byo)


def test_the_pipeline_uses_the_visitors_model_and_never_puts_the_key_in_an_event():
    b = Brain("anthropic", "claude-test", KEY)
    plan = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="men's kurta")])
    evs = list(run_pipeline("kurta", _services(lambda t, br: (plan, 0.5)), brain=b))
    u = next(e for e in evs if e["stage"] == "understand" and e["status"] == "done")
    assert u["payload"]["model"] == "claude-test (your Anthropic key)"
    assert KEY not in json.dumps(evs)


def test_a_failing_key_is_reported_in_words_and_the_search_still_runs():
    def boom(t, br):
        raise BrainError(f"the provider refused the key (401) {KEY}")

    evs = list(run_pipeline("kurta", _services(boom), brain=Brain("openai", "m", KEY, "https://x")))
    failed = next(e for e in evs if e["stage"] == "understand" and e["status"] == "failed")
    assert "refused the key" in failed["payload"]["error"] and KEY not in json.dumps(evs)
    assert any(e["stage"] == "search" and e["status"] == "done" for e in evs)     # the whole sentence was searched instead


def test_http_post_streams_with_the_key_and_a_bad_setting_is_refused_without_echo():
    plan = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="men's kurta")])
    client = TestClient(create_app(lambda: _services(lambda t, br: (plan, 0.1))))
    ok = client.post("/api/search", json={"q": "kurta", "brain": {"kind": "openai", "key": KEY, "model": "m", "base_url": "https://api.groq.com/openai/v1"}})
    assert ok.status_code == 200 and "(your provider key)" in ok.text and KEY not in ok.text
    bad = client.post("/api/search", json={"q": "kurta", "brain": {"kind": "openai", "key": KEY, "model": "bad model!"}})
    assert bad.status_code == 422 and KEY not in bad.text
    wrong_shape = client.post("/api/search", json={"q": "kurta", "brain": {"kind": 5, "key": KEY}})
    assert wrong_shape.status_code == 422 and KEY not in wrong_shape.text           # FastAPI's own validation error must not repeat the input
    assert client.get("/api/health").json()["byo"] is True


def test_anthropic_path_forces_the_plan_tool_and_hands_the_key_only_to_the_sdk(monkeypatch):
    import anthropic

    seen = {}

    class Block:
        type, input = "tool_use", PLAN

    class FakeAnthropic:
        def __init__(self, api_key, **kw):
            seen["key"], seen["kw"] = api_key, kw
            self.messages = self

        def create(self, **kw):
            seen["call"] = kw
            return type("R", (), {"content": [Block]})

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    plan = BrainChain(Brain("anthropic", "claude-test", KEY)).invoke({"system": "SYS", "request": "red kurta"})
    assert plan.gender == "men" and seen["key"] == KEY and seen["kw"]["max_retries"] == 0
    assert seen["call"]["tool_choice"] == {"type": "tool", "name": "answer"} and seen["call"]["max_tokens"] == 600
    assert KEY not in json.dumps(seen["call"], default=str)           # not in anything sent as the message


def test_anthropic_failure_does_not_leak_the_key(monkeypatch):
    import anthropic

    class Boom:
        def __init__(self, api_key, **kw):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError(f"401 invalid x-api-key {KEY}")

    monkeypatch.setattr(anthropic, "Anthropic", Boom)
    with pytest.raises(BrainError) as e:
        BrainChain(Brain("anthropic", "m", KEY)).invoke({"system": "s", "request": "r"})
    assert KEY not in str(e.value)


def test_a_provider_without_json_mode_is_asked_again_without_it():
    srv, seen = _provider(reject_json_mode=True)
    try:
        plan = BrainChain(Brain("openai", "m", KEY, f"http://127.0.0.1:{srv.server_port}/v1")).invoke({"system": "s", "request": "r"})
        assert plan.gender == "men" and seen["calls"] == 2 and "response_format" not in seen["body"]
    finally:
        srv.shutdown()


@pytest.mark.parametrize("wrapped", ["```json\n%s\n```", "Sure! Here is the plan:\n%s\nHope that helps.", "%s"])
def test_an_answer_wrapped_in_a_code_fence_or_a_sentence_is_still_read(wrapped):
    srv, _ = _provider(content=wrapped % json.dumps(PLAN))
    try:
        assert BrainChain(Brain("openai", "m", KEY, f"http://127.0.0.1:{srv.server_port}/v1")).invoke({"system": "s", "request": "r"}).pieces[0].kind == "top"
    finally:
        srv.shutdown()


def test_an_answer_with_no_json_at_all_is_said_in_words():
    srv, _ = _provider(content="I cannot help with that.")
    try:
        with pytest.raises(BrainError, match="did not answer with JSON"):
            BrainChain(Brain("openai", "m", KEY, f"http://127.0.0.1:{srv.server_port}/v1")).invoke({"system": "s", "request": "r"})
    finally:
        srv.shutdown()


def test_token_usage_is_reported_for_the_provider_bill():
    srv, _ = _provider(body={"choices": [{"message": {"content": json.dumps(PLAN)}}], "usage": {"prompt_tokens": 812, "completion_tokens": 97}})
    try:
        chain = BrainChain(Brain("openai", "m", KEY, f"http://127.0.0.1:{srv.server_port}/v1"))
        chain.invoke({"system": "s", "request": "r"})
        assert chain.usage == {"input_tokens": 812, "output_tokens": 97}
    finally:
        srv.shutdown()


def test_the_pipeline_puts_token_usage_in_the_understand_step_but_never_the_key():
    plan = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="men's kurta")])
    evs = list(run_pipeline("kurta", _services(lambda t, br: (plan, 0.5, {"input_tokens": 700, "output_tokens": 80})), brain=Brain("anthropic", "claude-test", KEY)))
    u = next(e for e in evs if e["stage"] == "understand" and e["status"] == "done")
    assert u["payload"]["usage"] == {"input_tokens": 700, "output_tokens": 80} and KEY not in json.dumps(evs)


def test_extra_hosts_can_be_added_by_the_server_owner(monkeypatch):
    monkeypatch.setenv("GENKART_BYO_HOSTS", "llm.internal.example")
    assert parse({"kind": "openai", "key": KEY, "base_url": "https://llm.internal.example/v1"}).base_url == "https://llm.internal.example/v1"


def _mock(handler):
    import httpx

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_list_models_asks_the_provider_filters_to_chat_models_and_strips_the_gemini_prefix():
    import httpx

    from genkart.brain import list_models

    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((str(req.url), req.headers.get("authorization")))
        return httpx.Response(200, json={"data": [{"id": "models/gemini-2.5-flash"}, {"id": "models/text-embedding-004"}, {"id": "gemini-2.5-pro"}, {"id": "models/imagen-4"}, {"id": "models/gemini-2.5-flash"}]})

    names = list_models(Brain("openai", "x", KEY, "https://generativelanguage.googleapis.com/v1beta/openai"), _mock(handler))
    assert names == ["gemini-2.5-flash", "gemini-2.5-pro"]                       # embeddings and image models left out, duplicates merged, prefix gone
    assert seen == [("https://generativelanguage.googleapis.com/v1beta/openai/models", f"Bearer {KEY}")]


def test_list_models_says_plainly_what_went_wrong_and_never_the_key():
    import httpx

    from genkart.brain import list_models

    for status, words in ((401, "refused the key"), (403, "may not use"), (404, "no model list"), (429, "too many requests"), (503, "problem on its side")):
        with pytest.raises(BrainError, match=words) as e:
            list_models(Brain("openai", "x", KEY, "https://api.example.com/v1"), _mock(lambda req, s=status: httpx.Response(s)))
        assert KEY not in str(e.value)

    def boom(req):
        raise httpx.ConnectError(f"cannot connect {KEY}")

    with pytest.raises(BrainError, match="could not get the model list") as e:
        list_models(Brain("openai", "x", KEY, "https://api.example.com/v1"), _mock(boom))
    assert KEY not in str(e.value)
    with pytest.raises(BrainError, match="no chat models"):
        list_models(Brain("openai", "x", KEY, "https://api.example.com/v1"), _mock(lambda req: httpx.Response(200, json={"data": [{"id": "text-embedding-3"}]})))


def test_a_wrong_model_name_is_explained_in_plain_words_not_with_library_text():
    import httpx

    with pytest.raises(BrainError) as e:
        BrainChain(Brain("openai", "3.5", KEY, "https://generativelanguage.googleapis.com/v1beta/openai"), _mock(lambda req: httpx.Response(404))).invoke({"system": "s", "request": "r"})
    msg = str(e.value)
    assert "does not know the model" in msg and "3.5" in msg and "Load my models" in msg
    assert "http" not in msg and KEY not in msg                                 # no addresses or links from the library's own text


def test_the_providers_own_reason_is_shown_short_and_without_the_key():
    import httpx

    def reply(status, body):
        return BrainChain(Brain("openai", "gemini-x", KEY, "https://generativelanguage.googleapis.com/v1beta/openai"), _mock(lambda req: httpx.Response(status, json=body))).invoke({"system": "s", "request": "r"})

    with pytest.raises(BrainError) as e:
        reply(400, [{"error": {"code": 400, "message": f"API key not valid. Please pass a valid API key. ({KEY})"}}])      # Gemini sends a list
    msg = str(e.value)
    assert "did not accept the request (400)" in msg and "API key not valid" in msg and KEY not in msg
    with pytest.raises(BrainError) as e:
        reply(400, {"error": {"message": "x" * 500}})                                                                      # OpenAI-style, and capped
    assert len(str(e.value)) < 400
    with pytest.raises(BrainError) as e:
        reply(400, {"unexpected": "shape"})                                                                                 # nothing known to add: just the plain sentence
    assert "The provider says" not in str(e.value)
