"""scripts/make_pilot_ratings_set.py: whitelist of keys, string ids, deterministic, counts equal the source files."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROMPT_KEYS = {"id", "test_set", "text", "source"}
RATING_KEYS = {"prompt_id", "test_set", "method", "rating", "product_ids"}
BANNED = ("title", "image", "path", "file", "name")


def build(out, *extra):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_pilot_ratings_set.py"), "--out", str(out), *extra], check=True, cwd=ROOT, capture_output=True)
    return {p.name: p.read_bytes() for p in sorted(pathlib.Path(out).iterdir())}


def jl(b):
    return [json.loads(l) for l in b.decode().splitlines()]


def test_whitelist_strings_and_counts(tmp_path):
    files = build(tmp_path / "o")
    assert set(files) == {"prompts.jsonl", "ratings.jsonl", "README.md", "LICENSE-NOTE.md"}
    prompts, ratings = jl(files["prompts.jsonl"]), jl(files["ratings.jsonl"])
    for p in prompts:
        assert set(p) == PROMPT_KEYS and p["source"] in {"author", "marqo-query", "llm-generated", "unknown"}
    for r in ratings:
        assert set(r) == RATING_KEYS and r["rating"] in {"good", "okay", "bad"}
        assert r["product_ids"] and all(isinstance(x, str) and x.isdigit() for x in r["product_ids"])
    for rec in prompts + ratings:
        assert not any(b in k.lower() for k in rec for b in BANNED)
    n4 = sum(1 for _ in open(ROOT / "runs/judge-validate.jsonl"))
    n5 = sum(1 for _ in open(ROOT / "runs/judge-test5.jsonl"))
    assert (n4, n5) == (141, 132)
    assert sum(r["test_set"] == "test4" for r in ratings) == n4
    assert sum(r["test_set"] == "test5" for r in ratings) == n5
    assert all(p["text"] is None for p in prompts if p["test_set"] == "test5")
    assert all(isinstance(p["text"], str) for p in prompts if p["test_set"] == "test4")


def test_deterministic_and_prompts_flag(tmp_path):
    assert build(tmp_path / "a") == build(tmp_path / "b")
    f = tmp_path / "p5.txt"
    f.write_text("# header\n" + "\n".join(f"prompt {i}" for i in range(1, 51)) + "\n")
    out = jl(build(tmp_path / "c", "--prompts", str(f))["prompts.jsonl"])
    assert [p["text"] for p in out if p["test_set"] == "test5"][:2] == ["prompt 1", "prompt 2"]
