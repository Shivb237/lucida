"""The study's answer storage: the local file store (replace, delete, survive a damaged line) and the Firestore store's requests, checked against a fake Google."""
import json

import httpx
import pytest

from genkart.studystore import FirestoreStore, JsonlStore, make_store


def test_jsonl_store_saves_replaces_and_deletes(tmp_path):
    s = JsonlStore(str(tmp_path / "a.jsonl"))
    s.save("answers", "p1__7", {"rating": 3})
    s.save("answers", "p1__8", {"rating": 5})
    s.save("answers", "p1__7", {"rating": 4})             # the same answer sent again replaces the first
    rows = [json.loads(line) for line in (tmp_path / "a.jsonl").read_text().splitlines()]
    assert sorted((r["_id"], r["rating"]) for r in rows) == [("p1__7", 4), ("p1__8", 5)]
    s.delete("answers", "p1__7")
    s.delete("answers", "never-existed")                  # deleting nothing is fine
    assert [json.loads(line)["_id"] for line in (tmp_path / "a.jsonl").read_text().splitlines()] == ["p1__8"]


def test_jsonl_store_skips_a_damaged_line(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_text('{"_collection": "answers", "_id": "x", "rating": 1}\n{"half a li')
    JsonlStore(str(f)).save("answers", "y", {"rating": 2})
    assert [json.loads(line)["_id"] for line in f.read_text().splitlines()] == ["x", "y"]


def _fake_google(seen, fail_on=None):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, str(req.url), req.headers.get("authorization"), req.content))
        if req.url.host == "metadata.google.internal":
            assert req.headers["metadata-flavor"] == "Google"
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3000}) if req.url.path.endswith("/token") else httpx.Response(200, text="my-project")
        if fail_on and req.method == fail_on:
            return httpx.Response(503)
        return httpx.Response(404 if req.method == "DELETE" else 200, json={})
    return handler


def test_firestore_store_sends_the_right_requests():
    seen = []
    s = FirestoreStore(httpx.Client(transport=httpx.MockTransport(_fake_google(seen))))
    s.save("study_answers", "p1__7", {"rating": 4, "arm": "with", "seconds": 12.5, "ok": True})
    s.save("study_answers", "p1__8", {"rating": 2})
    s.delete("study_answers", "p1__7")                    # Google answers 404: nothing to delete, not an error
    patch = [x for x in seen if x[0] == "PATCH"][0]
    assert patch[1] == "https://firestore.googleapis.com/v1/projects/my-project/databases/(default)/documents/study_answers/p1__7"
    assert patch[2] == "Bearer tok"
    assert json.loads(patch[3]) == {"fields": {"rating": {"integerValue": "4"}, "arm": {"stringValue": "with"}, "seconds": {"doubleValue": 12.5}, "ok": {"booleanValue": True}}}
    assert sum(1 for x in seen if x[1].endswith("/token")) == 1            # the token is fetched once and reused


def test_firestore_store_raises_when_google_fails():
    s = FirestoreStore(httpx.Client(transport=httpx.MockTransport(_fake_google([], fail_on="PATCH"))))
    with pytest.raises(httpx.HTTPStatusError):
        s.save("study_answers", "p1__7", {"rating": 4})


def test_make_store_choices(tmp_path):
    assert make_store("") is None
    assert isinstance(make_store(f"jsonl:{tmp_path}/x.jsonl"), JsonlStore)
    assert isinstance(make_store("firestore"), FirestoreStore)
    with pytest.raises(SystemExit):
        make_store("mysql")
