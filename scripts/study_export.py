"""Download the study's answers from Firestore (yours: you run this, signed in with `gcloud auth login`) and summarise them honestly.

Writes data/study/export.jsonl (git-ignored: answers never go in the repository) and runs/study.summary.json (counts and the with-minus-without difference with its interval).
Usage: .venv/bin/python scripts/study_export.py [project-id]        (default: the gcloud project)
"""
import json
import pathlib
import subprocess
import sys

import httpx

sys.path.insert(0, "src")
from genkart.studystats import analyse  # noqa: E402


def gcloud(*args: str) -> str:
    return subprocess.run(["gcloud", *args], capture_output=True, text=True, check=True).stdout.strip()


def untyped(v: dict):
    (kind, val), = v.items()
    return int(val) if kind == "integerValue" else val


project = sys.argv[1] if len(sys.argv) > 1 else gcloud("config", "get-value", "project")
token = gcloud("auth", "print-access-token")
rows, page = [], None
while True:
    r = httpx.get(f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents/study_answers", headers={"authorization": f"Bearer {token}"},
                  params={"pageSize": 300, **({"pageToken": page} if page else {})}, timeout=30)
    r.raise_for_status()
    d = r.json()
    rows += [{"_collection": "study_answers", **{k: untyped(v) for k, v in doc["fields"].items()}} for doc in d.get("documents", [])]
    page = d.get("nextPageToken")
    if not page:
        break
out = pathlib.Path("data/study")
out.mkdir(parents=True, exist_ok=True)
(out / "export.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
summary = {"project": project, "source": "Firestore study_answers", **analyse(rows)}
pathlib.Path("runs").mkdir(exist_ok=True)
json.dump(summary, open("runs/study.summary.json", "w"), indent=2)
print(json.dumps(summary, indent=2))
