"""One JSON log line per request with its ticket number; hostile ticket numbers cannot forge log lines."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from genkart.reqlog import install


def make():
    app = FastAPI()
    install(app, "demo", shard=2)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/work")
    def work():
        return {"done": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("bug")

    return TestClient(app, raise_server_exceptions=False)


def lines(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


def test_a_request_logs_one_json_line_with_the_ticket_number(capsys):
    make().post("/work", headers={"x-request-id": "abc123"})
    [row] = lines(capsys)
    assert row["req"] == "abc123" and row["svc"] == "demo" and row["shard"] == 2 and row["path"] == "/work" and row["status"] == 200 and row["ms"] >= 0


def test_health_checks_are_not_logged(capsys):
    make().get("/health")
    assert lines(capsys) == []


def test_a_crashing_handler_is_still_logged_as_500(capsys):
    r = make().get("/boom", headers={"x-request-id": "t1"})
    assert r.status_code == 500
    [row] = lines(capsys)
    assert row["req"] == "t1" and row["status"] == 500


def test_a_hostile_ticket_cannot_inject_extra_log_lines_and_is_cut_short(capsys):
    make().post("/work", headers={"x-request-id": "x" * 500})
    make().post("/work", headers={"x-request-id": 'a","status":999,"evil":"1'})
    rows = lines(capsys)
    assert len(rows) == 2 and len(rows[0]["req"]) == 64
    assert rows[1]["status"] == 200 and "evil" not in rows[1]     # the quote characters stayed inside the string
