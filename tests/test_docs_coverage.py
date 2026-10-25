"""The documentation must cover the project: every code file is on the map with a description, every logged run is cited by the site
(or excluded here with a reason), and everything the site cites exists. A new file or run that is not documented fails this test."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAP = json.load(open(ROOT / "web/src/content/map.json"))
SITE_SOURCES = [p for p in (ROOT / "web/src").rglob("*") if p.suffix in (".ts", ".tsx") and "node_modules" not in p.parts]
SITE_TEXT = "\n".join(p.read_text() for p in SITE_SOURCES) + "\n" + (ROOT / "web/vite.config.ts").read_text()

# Runs that are on purpose not cited by the site, each with the reason (a new summary file is NOT silently excluded: add it here or cite it).
NOT_CITED = {
    "blind-test6.summary.json": "tiny-photo A/B (blind test 6, 2026-10-25): removal did not improve ratings; cited after it is added to the Evidence page",
    "blur-exposure.summary.json": "how often tiny Kaggle photos are shown (blur investigation, 2026-10-25); cited after the blind test 6 decision",
    "blur-exposure-no-kaggle.summary.json": "the same search with the tiny Kaggle photos switched off (blur investigation); cited after the blind test 6 decision",
    "random.summary.json": "pilot baseline, shown on the Evidence page by key",
    "bm25.summary.json": "pilot baseline, shown on the Evidence page by key",
    "siglip-base.summary.json": "pilot baseline, shown on the Evidence page by key",
    "marqo-fashionsiglip-title.summary.json": "pilot variant (query vs title), described in README only",
    "marqo-fashionsiglip-fused.summary.json": "pilot variant (photo plus title), described in README only",
    "m4-heldout.pre-fix.summary.json": "superseded by m4-heldout.summary.json, kept as a record",
    "m4-heldout.summary.json": "held-out understanding run; the rated version is cited",
    "ingest.run1-fixed-3-retries.summary.json": "cited by name on the System page",
    "data-quality.summary.json": "pilot data-quality check, cited in the build log",
    "data-quality-all.summary.json": "combined data-quality pass, cited in the build log",
    "data-quality-4.summary.json": "four-catalogue data-quality pass; the Docs numbers are read from the map and the build log",
    "duplicates.summary.json": "duplicate analysis, cited in the build log",
    "kaggle-attr.summary.json": "Kaggle attribute check, cited in the build log",
    "myntra2-alignment.summary.json": "Myntra image/CSV alignment check, cited in the build log",
    "claude-vs-qwen-judged.summary.json": "judge-scored comparison; the Docs text uses the human result instead",
    "claude-vs-qwen.summary.json": "kept-words comparison read by the evidence module",
    "judge-validate.summary.json": "first judge validation; the later fresh-set check is cited",
    "aws-cw-test.jsonl": "scratch run while setting up CloudWatch, no result",
    "aws-cw-test2.jsonl": "scratch run while setting up CloudWatch, no result",
    "aws-dash.jsonl": "traffic made to fill the dashboard for screenshots",
    "aws-healthy.jsonl": "earlier healthy probe; the first run in aws-failover.jsonl is shown",
    "aws-rebuilt.jsonl": "probe after the rebuild; the rebuilt load test is cited",
    "aws-trace.jsonl": "one traced request used for the screenshot, no result",
    "aws-demo-2026-10-16.jsonl": "the 90-search failover demo recorded for screenshots; the full failover runs are shown",
    "test5-build.summary.json": "how the test-5 sheet was built (counts of identical options, spend); its results are cited through blind-test5.summary.json",
    "aws-loadtest.jsonl": "raw log of the load test whose table is cited through aws-loadtest.summary.json",
}


def test_every_code_file_is_on_the_map_with_a_description():
    mapped = {f["path"] for a in MAP["areas"] for f in a["files"]}
    exts = {"src/genkart/": (".py",), "scripts/": (".py", ".sh"), "services/router/src/": (".ts",), "infra/lib/": (".ts",), "tests/": (".py",)}
    missing = []
    for prefix, ex in exts.items():
        for p in sorted((ROOT / prefix).rglob("*")):
            if p.is_file() and p.suffix in ex and p.name != "__init__.py" and "__pycache__" not in p.parts and "node_modules" not in p.parts:
                if str(p.relative_to(ROOT)) not in mapped:
                    missing.append(str(p.relative_to(ROOT)))
    assert not missing, f"not on the map (run: .venv/bin/python scripts/build_map.py <graph.json>): {missing}"
    assert all(f["does"] for a in MAP["areas"] for f in a["files"]), "a file on the map has no description"


def test_every_logged_run_is_cited_or_excluded_with_a_reason():
    uncited = []
    for p in sorted((ROOT / "runs").iterdir()):
        if p.name in NOT_CITED or not (p.name.endswith(".summary.json") or p.name.startswith("aws-")):
            continue
        if p.name not in SITE_TEXT:
            uncited.append(p.name)
    assert not uncited, f"runs the site never cites (cite them in web/src/content/docs.ts or add to NOT_CITED with a reason): {uncited}"


def test_every_run_the_site_cites_exists():
    cited = set(re.findall(r"runs/([A-Za-z0-9_.+-]+\.(?:summary\.json|jsonl|json))", SITE_TEXT))
    gone = sorted(c for c in cited if not (ROOT / "runs" / c).exists())
    assert not gone, f"the site cites runs that do not exist: {gone}"


def test_the_recorded_runs_contain_no_photo_address_and_no_closed_catalogue_id():
    raw = (ROOT / "web/src/recorded/runs.json").read_text()
    assert "/api/image" not in raw and "http" not in raw
    data = json.loads(raw)
    for run in data["runs"]:
        for e in run["events"]:
            if e.get("kind") == "step" and e["stage"] == "search" and e["status"] == "done":
                for piece in e["payload"]["pieces"]:
                    for h in piece["hits"]:
                        if h["source"] != "marqo":
                            assert h["id"].startswith(h["source"] + "-p") and "not republished" in h["title"]
