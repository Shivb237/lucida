"""Where the consented study keeps its answers. Two places, one small interface (save / has / delete a document by id, delete_many in one request):
  JsonlStore      a local file, for trying the study on your own computer and for tests (GENKART_STUDY=jsonl:data/study/answers.jsonl)
  FirestoreStore  Google Firestore in the project the server runs in (GENKART_STUDY=firestore). It speaks Firestore's plain web interface with httpx and the
                  token of the service account the server runs as (read from Google's metadata server), so no extra package is installed.
Nothing here ever sees or stores a network address or a name: callers pass only the fields they want kept.
"""
from __future__ import annotations

import json
import pathlib
import threading
import time
import urllib.parse

import httpx

API = "https://firestore.googleapis.com/v1"
META = "http://metadata.google.internal/computeMetadata/v1"


class JsonlStore:
    def __init__(self, path: str):
        self.path, self.lock = pathlib.Path(path), threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue          # a half-written line (crash mid-write) is skipped, not fatal
        return out

    def save(self, collection: str, doc_id: str, doc: dict) -> None:
        with self.lock:
            rows = [r for r in self._rows() if not (r["_collection"] == collection and r["_id"] == doc_id)]      # same id replaces: a resubmitted answer is not counted twice
            rows.append({"_collection": collection, "_id": doc_id, **doc})
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
            tmp.replace(self.path)

    def has(self, collection: str, doc_id: str) -> bool:
        with self.lock:
            return any(r["_collection"] == collection and r["_id"] == doc_id for r in self._rows())

    def delete(self, collection: str, doc_id: str) -> None:
        self.delete_many([(collection, doc_id)])

    def delete_many(self, docs: list[tuple[str, str]]) -> None:
        gone = set(docs)
        with self.lock:
            rows = [r for r in self._rows() if (r["_collection"], r["_id"]) not in gone]
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
            tmp.replace(self.path)


def _typed(v):
    """A Python value as a Firestore field value."""
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


class FirestoreStore:
    def __init__(self, client: httpx.Client | None = None, project: str | None = None):
        self.http = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=3.0))      # a slow database must not hold a visitor's request for long
        self._project, self._token, self._expires = project, None, 0.0
        self.lock = threading.Lock()

    def _meta(self, path: str) -> httpx.Response:
        r = self.http.get(f"{META}/{path}", headers={"Metadata-Flavor": "Google"})
        r.raise_for_status()
        return r

    def _auth(self) -> dict:
        with self.lock:
            if self._token is None or time.monotonic() > self._expires - 60:       # refresh a minute early
                t = self._meta("instance/service-accounts/default/token").json()
                self._token, self._expires = t["access_token"], time.monotonic() + float(t.get("expires_in", 300))
            if self._project is None:
                self._project = self._meta("project/project-id").text.strip()
            return {"authorization": f"Bearer {self._token}"}

    def _name(self, collection: str, doc_id: str) -> str:
        return f"projects/{self._project}/databases/(default)/documents/{collection}/{urllib.parse.quote(doc_id, safe='')}"

    def _url(self, collection: str, doc_id: str) -> str:
        return f"{API}/{self._name(collection, doc_id)}"

    def save(self, collection: str, doc_id: str, doc: dict) -> None:
        headers = self._auth()
        r = self.http.patch(self._url(collection, doc_id), headers=headers, json={"fields": {k: _typed(v) for k, v in doc.items()}})      # no field mask: creates or replaces
        r.raise_for_status()

    def has(self, collection: str, doc_id: str) -> bool:
        headers = self._auth()
        r = self.http.get(self._url(collection, doc_id), headers=headers, params={"mask.fieldPaths": "ts"})     # one small field: existence is all we need
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return True

    def delete(self, collection: str, doc_id: str) -> None:
        headers = self._auth()
        r = self.http.delete(self._url(collection, doc_id), headers=headers)
        if r.status_code != 404:       # nothing to delete is fine
            r.raise_for_status()

    def delete_many(self, docs: list[tuple[str, str]]) -> None:
        """Every delete in ONE commit (atomic: all or none). Deleting a document that does not exist is not an error in a commit."""
        headers = self._auth()
        r = self.http.post(f"{API}/projects/{self._project}/databases/(default)/documents:commit", headers=headers,
                           json={"writes": [{"delete": self._name(c, d)} for c, d in docs]})
        r.raise_for_status()


def make_store(spec: str):
    """From GENKART_STUDY: '' (study off), 'jsonl:<path>' or 'firestore'."""
    if not spec:
        return None
    if spec == "firestore":
        return FirestoreStore()
    if spec.startswith("jsonl:"):
        return JsonlStore(spec[len("jsonl:"):])
    raise SystemExit(f"GENKART_STUDY must be empty, 'firestore' or 'jsonl:<path>', got {spec!r}")
