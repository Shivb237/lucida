"""Build the project map for the Docs page: web/src/content/map.json.

Every code file gets its own one-line description (the first docstring or comment line in the file, so the map cannot drift from the code)
and the files it imports, taken from a local code graph: a JSON file with "nodes" and "links" (an import graph of this repo, built on this computer) whose path is the one argument.
The finished map is committed (web/src/content/map.json); this script only needs re-running when files are added.
Usage: .venv/bin/python scripts/build_map.py path/to/graph.json
"""
import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GRAPH = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
AREAS = [  # (id, title, what it is, path prefix, extensions)
    ("pipeline", "Pipeline and services (Python)", "The steps of a search, the web server, and the processes the cluster is made of.", "src/genkart/", (".py",)),
    ("scripts", "Scripts", "One command per experiment, data build, test run or cloud task. Each writes its result to runs/.", "scripts/", (".py", ".sh")),
    ("router", "Router (TypeScript)", "Asks all shards at once, merges the answers, survives failures.", "services/router/src/", (".ts",)),
    ("infra", "AWS stacks (TypeScript, CDK)", "The cloud machines, network, queue and monitoring as code.", "infra/lib/", (".ts",)),
    ("web", "This website (TypeScript, React)", "Pages and parts of the site you are reading.", "web/src/", (".ts", ".tsx")),
    ("tests", "Tests", "What is checked on every change.", "tests/", (".py",)),
]
# Files that must not be edited just to add a comment (the router and the AWS stacks are deployed as they are): described here, in plain sight.
OVERRIDES = {
    "services/router/src/config.ts": "Router settings read from the environment: ports, shard addresses (with replicas), deadlines, hedge delay, in-flight limit.",
    "services/router/src/index.ts": "Starts the router process.",
    "services/router/src/server.ts": "The router: asks the encoder, asks every shard at once (failover and hedging across replicas), merges, refuses past the limit with HTTP 429.",
    "infra/lib/compute-stack.ts": "The three machines (router host, shard hosts in two zones) with their startup scripts and permissions.",
    "infra/lib/data-stack.ts": "The storage and queues: the photo bucket, the ingestion queue and its dead-letter queue.",
    "infra/lib/observability-stack.ts": "Logs, metric filters, the dashboard and alarms, and the budget alert.",
}
SKIP = ("__init__.py", "evidence.d.ts", "main.tsx")


def describe(path: pathlib.Path) -> str:
    rel = str(path.relative_to(ROOT))
    if rel in OVERRIDES:
        return OVERRIDES[rel]
    text = path.read_text(errors="ignore")
    if path.suffix == ".py":
        try:
            doc = ast.get_docstring(ast.parse(text))
        except SyntaxError:
            doc = None
        if doc:
            return re.sub(r"\s+", " ", doc.strip().splitlines()[0]).strip()
    elif path.suffix == ".sh":
        for line in text.splitlines()[1:6]:
            if line.startswith("#") and not line.startswith("#!") and len(line.strip("# ")) > 3:
                return line.strip("# ").strip()
    else:
        for line in text.splitlines()[:8]:
            s = line.strip()
            if s.startswith("//"):
                return s.lstrip("/ ").strip()
            if s.startswith("/**") or s.startswith("/*"):
                return re.sub(r"^/\*+\s*|\s*\*+/$", "", s).strip()
    return ""


def main() -> None:
    if GRAPH is None:
        raise SystemExit("usage: build_map.py path/to/graph.json")
    graph = json.load(open(GRAPH))
    node_file = {n["id"]: n.get("source_file") for n in graph["nodes"]}
    imports: dict[str, set[str]] = {}
    for l in graph["links"]:
        if l.get("relation") in ("imports", "imports_from"):
            a, b = node_file.get(l["source"]), node_file.get(l["target"])
            if a and b and a != b:
                imports.setdefault(a, set()).add(b)
    areas = []
    for aid, title, what, prefix, exts in AREAS:
        files = []
        for p in sorted((ROOT / prefix).rglob("*")):
            if not p.is_file() or p.suffix not in exts or p.name in SKIP or "node_modules" in p.parts or "__pycache__" in p.parts:
                continue
            if aid == "web" and "content" in p.parts:
                continue
            rel = str(p.relative_to(ROOT))
            files.append({"path": rel, "does": describe(p), "lines": len(p.read_text(errors="ignore").splitlines()),
                          "uses": sorted(imports.get(rel, []))})
        areas.append({"id": aid, "title": title, "what": what, "files": files})
    out = {"graph": {"nodes": len(graph["nodes"]), "links": len(graph["links"])}, "areas": areas}
    dest = ROOT / "web" / "src" / "content" / "map.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    missing = [f["path"] for a in areas for f in a["files"] if not f["does"]]
    print(f"{sum(len(a['files']) for a in areas)} files in {len(areas)} areas; {len(missing)} without a description")
    for m in missing:
        print("  no description:", m)


if __name__ == "__main__":
    main()
