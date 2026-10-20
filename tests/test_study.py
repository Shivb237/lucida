"""The consented study's server side: off unless configured, input checked, one answer per participant and prompt, withdrawal deletes, a failing store says 503."""
import json

import pytest
from fastapi.testclient import TestClient

from genkart import study
from genkart.server import create_app

from test_server import make_services

CODE = "3f2b8c1e-5a47-4d09-9c1e-7a6b2d8e4f10"
OTHER = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _app(tmp_path, monkeypatch, enabled=True):
    d = tmp_path / "data" / "study"
    d.mkdir(parents=True)
    (d / "prompts.json").write_text(json.dumps([{"query_id": 7, "query": "linen shirt"}, {"query_id": 8, "query": "wool coat"}]))
    if enabled:
        monkeypatch.setenv("GENKART_STUDY", f"jsonl:{tmp_path}/answers.jsonl")
    else:
        monkeypatch.delenv("GENKART_STUDY", raising=False)
    return TestClient(create_app(lambda: make_services(), root=tmp_path))


def _rows(tmp_path):
    f = tmp_path / "answers.jsonl"
    return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []


def _answer(**kw):
    return {"participant": CODE, "consent_version": study.CONSENT_VERSION, "query_id": "7", "arm": "with", "rating": 4, "position": 0, "seconds": 9.26, **kw}


def test_study_is_off_unless_configured(tmp_path, monkeypatch):
    c = _app(tmp_path, monkeypatch, enabled=False)
    assert c.get("/api/study/status").json()["enabled"] is False and c.get("/api/health").json()["study"] is False
    assert c.get("/api/study/items").status_code == 404
    assert c.post("/api/study/answer", json=_answer()).status_code == 404


def test_items_carry_the_prompt_the_drawing_and_identical_hits(tmp_path, monkeypatch):
    c = _app(tmp_path, monkeypatch)
    assert c.get("/api/health").json()["study"] is True
    body = c.get("/api/study/items").json()
    assert body["consent_version"] == study.CONSENT_VERSION and [i["query"] for i in body["items"]] == ["linen shirt", "wool coat"]
    assert body["items"][0]["drawing"] == "drawings/7.jpg" and body["items"][0]["hits"]


def test_an_answer_is_stored_once_with_only_the_allowed_fields(tmp_path, monkeypatch):
    c = _app(tmp_path, monkeypatch)
    assert c.post("/api/study/consent", json={"participant": CODE, "consent_version": study.CONSENT_VERSION}).status_code == 200
    assert c.post("/api/study/answer", json=_answer()).status_code == 200
    assert c.post("/api/study/answer", json=_answer(rating=2)).status_code == 200      # sent again (a retry): replaces, not a second answer
    a = [r for r in _rows(tmp_path) if r["_collection"] == "study_answers"]
    assert len(a) == 1 and a[0]["rating"] == 2 and a[0]["_id"] == f"{CODE}__7"
    assert set(a[0]) == {"_collection", "_id", "participant", "query_id", "arm", "rating", "position", "seconds", "consent_version", "ts"}     # no address, no name, no text
    assert a[0]["seconds"] == 9.3


@pytest.mark.parametrize("bad", [{"rating": 6}, {"rating": 0}, {"arm": "both"}, {"participant": "not-a-code"}, {"query_id": "999"}, {"seconds": -1}, {"position": 100}])
def test_bad_answers_are_refused_and_nothing_is_stored(tmp_path, monkeypatch, bad):
    c = _app(tmp_path, monkeypatch)
    assert c.post("/api/study/answer", json=_answer(**bad)).status_code == 422
    assert _rows(tmp_path) == []


def test_an_old_consent_text_is_refused(tmp_path, monkeypatch):
    c = _app(tmp_path, monkeypatch)
    assert c.post("/api/study/answer", json=_answer(consent_version="old")).status_code == 409
    assert c.post("/api/study/consent", json={"participant": CODE, "consent_version": "old"}).status_code == 409


def test_withdraw_deletes_only_that_participants_answers(tmp_path, monkeypatch):
    c = _app(tmp_path, monkeypatch)
    for who in (CODE, OTHER):
        c.post("/api/study/consent", json={"participant": who, "consent_version": study.CONSENT_VERSION})
        c.post("/api/study/answer", json=_answer(participant=who))
        c.post("/api/study/answer", json=_answer(participant=who, query_id="8"))
    assert c.post("/api/study/withdraw", json={"participant": CODE}).status_code == 200
    left = {r["_id"] for r in _rows(tmp_path)}
    assert left == {OTHER, f"{OTHER}__7", f"{OTHER}__8"}


def test_a_failing_store_answers_503_not_a_crash(tmp_path, monkeypatch):
    class Broken:
        def save(self, *a):
            raise RuntimeError("database down")

        has = delete = delete_many = save

    monkeypatch.setattr(study, "make_store", lambda spec: Broken())
    c = _app(tmp_path, monkeypatch)
    assert c.post("/api/study/answer", json=_answer()).status_code == 503
    assert c.post("/api/study/withdraw", json={"participant": CODE}).status_code == 503


def _consent(c, who=CODE):
    return c.post("/api/study/consent", json={"participant": who, "consent_version": study.CONSENT_VERSION})


def test_a_daily_cap_stops_a_flood_of_writes_and_counts_each_document_once(tmp_path, monkeypatch):
    monkeypatch.setenv("GENKART_STUDY_MAX_PER_DAY", "3")
    c = _app(tmp_path, monkeypatch)
    assert _consent(c).status_code == 200                                              # 1
    assert c.post("/api/study/answer", json=_answer()).status_code == 200              # 2
    assert c.post("/api/study/answer", json=_answer(rating=1)).status_code == 200      # the same answer again: replaces itself, still 2
    assert c.post("/api/study/answer", json=_answer(query_id="8")).status_code == 200  # 3
    r = _consent(c, OTHER)
    assert r.status_code == 503 and "full for today" in r.json()["detail"]
    assert len(_rows(tmp_path)) == 3


def test_an_answer_needs_a_consent_on_record(tmp_path, monkeypatch):
    c = _app(tmp_path, monkeypatch)
    r = c.post("/api/study/answer", json=_answer())
    assert r.status_code == 403 and "consent" in r.json()["detail"] and _rows(tmp_path) == []
    assert _consent(c).status_code == 200 and c.post("/api/study/answer", json=_answer()).status_code == 200
    # a second server (another instance behind the same store) finds the consent in the store, not in its memory
    c2 = TestClient(create_app(lambda: make_services(), root=tmp_path))
    assert c2.post("/api/study/answer", json=_answer(query_id="8")).status_code == 200
    assert c2.post("/api/study/withdraw", json={"participant": CODE}).status_code == 200
    assert c2.post("/api/study/answer", json=_answer()).status_code == 403              # withdrawn: the consent is gone too


def test_withdraw_is_one_batch_request(tmp_path, monkeypatch):
    calls = []

    class Store:
        def save(self, *a):
            calls.append("save")

        def has(self, *a):
            return True

        def delete(self, *a):
            calls.append("delete")

        def delete_many(self, docs):
            calls.append(("delete_many", sorted(docs)))

    monkeypatch.setattr(study, "make_store", lambda spec: Store())
    c = _app(tmp_path, monkeypatch)
    assert c.post("/api/study/withdraw", json={"participant": CODE}).status_code == 200
    assert calls == [("delete_many", [("study_answers", f"{CODE}__7"), ("study_answers", f"{CODE}__8"), ("study_participants", CODE)])]


def test_firestore_withdraw_is_one_commit_and_has_reads_one_document():
    import httpx

    from genkart.studystore import FirestoreStore

    seen = []

    def handler(req: httpx.Request):
        seen.append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        if req.url.path.endswith("/study_participants/nobody"):
            return httpx.Response(404, json={})
        return httpx.Response(200, json={})

    fs = FirestoreStore(httpx.Client(transport=httpx.MockTransport(handler)), project="p")
    fs._token, fs._expires = "t", float("inf")
    fs.delete_many([("study_answers", "a__7"), ("study_participants", "a")])
    assert len(seen) == 1 and seen[0][0] == "POST" and seen[0][1].endswith("/documents:commit")
    assert [w["delete"] for w in seen[0][2]["writes"]] == ["projects/p/databases/(default)/documents/study_answers/a__7",
                                                          "projects/p/databases/(default)/documents/study_participants/a"]
    assert fs.has("study_participants", "a") is True and fs.has("study_participants", "nobody") is False


def test_a_withdrawal_on_another_instance_stops_answers_here_too(tmp_path, monkeypatch):
    """Instance A took the consent and an answer; the participant withdraws through instance B (same store). A must refuse the next answer:
    it asks the store on every answer instead of remembering the consent."""
    a = _app(tmp_path, monkeypatch)
    assert _consent(a).status_code == 200 and a.post("/api/study/answer", json=_answer()).status_code == 200
    b = TestClient(create_app(lambda: make_services(), root=tmp_path))
    assert b.post("/api/study/withdraw", json={"participant": CODE}).status_code == 200
    r = a.post("/api/study/answer", json=_answer(query_id="8"))
    assert r.status_code == 403 and [x for x in _rows(tmp_path) if x["_collection"] == "study_answers"] == []
