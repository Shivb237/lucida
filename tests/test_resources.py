"""The memory numbers come from the operating system and Ollama's own report: a snapshot must be well formed even with nothing running."""
import os

from fastapi.testclient import TestClient

from genkart import resources
from genkart.server import create_app
from test_server import make_services


def test_snapshot_reads_this_process_and_the_pid_files_and_ollama_report(tmp_path):
    (tmp_path / "data" / "run").mkdir(parents=True)
    (tmp_path / "data" / "run" / "encoder.pid").write_text(str(os.getpid()))
    (tmp_path / "data" / "run" / "gone.pid").write_text("999999")           # a process that is not running is left out, not guessed
    (tmp_path / "data" / "run" / "junk.pid").write_text("not a number")
    snap = resources.snapshot(tmp_path, {"models": [{"name": "qwen3:4b-instruct", "size": 2_600_000_000, "size_vram": 2_500_000_000}]})
    assert snap["server"]["rss_mb"] > 10 and snap["server"]["peak_mb"] >= snap["server"]["rss_mb"] * 0.5
    assert [c["name"] for c in snap["cluster"]] == ["encoder"]
    assert snap["ollama"] == [{"name": "qwen3:4b-instruct", "size_mb": 2600, "vram_mb": 2500}]
    assert snap["computer"]["cpus"] and snap["computer"]["memory_gb"] > 0


def test_snapshot_without_ollama_or_cluster(tmp_path):
    snap = resources.snapshot(tmp_path, None)
    assert snap["ollama"] == [] and snap["cluster"] == []


def test_the_http_route_answers(tmp_path):
    body = TestClient(create_app(lambda: make_services(), root=tmp_path)).get("/api/resources").json()
    assert set(body) == {"server", "ollama", "cluster", "computer"}
