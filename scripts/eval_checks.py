"""How often the top picks break a plain rule, before and after the candidate checks (src/genkart/checks.py). A COUNT of rule breaks, not a quality rating.

For each request: the local model's plan (Qwen3 4B via Ollama) and the clothes map, as the Lab runs them; the search's candidates; then the checks.
Counted on the first pick of every piece: a garment whose title names another kind than its slot; a children's item for a request not about a child;
an outfit mixing men's and women's items; a named colour the photo does not show. Prompts: test sets 4 and 5 (already used for the blind tests; fine for
counting rule breaks, not for judging quality). Writes runs/checks-eval.jsonl (one line per request) and runs/checks-eval.summary.json.
Usage: .venv/bin/python scripts/eval_checks.py
"""
import datetime
import json
import pathlib
import sys

sys.path.insert(0, "src")
from genkart import checks  # noqa: E402
from genkart.catalogue import title_gender  # noqa: E402
from genkart.server import default_services  # noqa: E402

prompts = [l.strip() for f in ("data/human_prompts_test4.txt", "data/human_prompts_test5.txt") for l in open(f) if l.strip() and not l.startswith("#")]
svc = default_services()
K = 6


def breaks(kinds, colours, firsts, text):
    kind = sum(1 for kd, h in zip(kinds, firsts) if not checks.fits_kind(h.title, kd))
    child = sum(1 for h in firsts if title_gender(h.title) in {"Boys", "Girls", "Kids"}) if not checks._CHILD_REQUEST.search(text) else 0
    gs = {title_gender(h.title) for h in firsts} & {"Men", "Women"}
    mixed = int(len(gs) == 2)
    named = [(kd, w, h) for kd, w, h in zip(kinds, colours, firsts) if w and set().union(*(checks.COLOUR_FAMILY.get(x.lower(), set()) for x in w))]
    colour_miss = sum(1 for kd, w, h in named if getattr(svc.colour(h, kd), "name", None) not in set().union(*(checks.COLOUR_FAMILY.get(x.lower(), set()) for x in w)))
    return {"wrong_slot": kind, "child_for_adult": child, "mixed_gender_outfit": mixed, "colour_missing": colour_miss, "colour_named": len(named)}


rows = []
for i, q in enumerate(prompts, 1):
    plan, _ = svc.understand(q)
    try:
        plan = svc.expand(plan, q)[0]
    except LookupError:
        pass
    pieces = [p for p in plan.pieces if p.search_text.strip()]
    found = svc.search([p.search_text for p in pieces], plan.gender if plan.gender != "unknown" else None, 2 * K)
    kinds, colours = [p.kind for p in pieces], [p.colours for p in pieces]
    after, notes = checks.apply(kinds, colours, found.pieces, plan.gender, q, svc.colour, K)
    before = [hs[:K] for hs in found.pieces]
    row = {"prompt": q, "gender": plan.gender, "pieces": [p.search_text for p in pieces],
           "before": breaks(kinds, colours, [hs[0] for hs in before if hs], q), "after": breaks(kinds, colours, [hs[0] for hs in after if hs], q), "notes": notes}
    rows.append(row)
    print(f"[{i}/{len(prompts)}] {q[:50]!r}: before {row['before']} after {row['after']}", flush=True)

pathlib.Path("runs").mkdir(exist_ok=True)
with open("runs/checks-eval.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
tot = lambda side, key: sum(r[side][key] for r in rows)  # noqa: E731
summary = {"setup": {"what": "rule breaks in the FIRST pick of every piece, before vs after the candidate checks; a count, not a quality rating",
                     "prompts": len(rows), "sources": ["data/human_prompts_test4.txt", "data/human_prompts_test5.txt"], "understand": "local Qwen3 4B (Ollama)",
                     "k": K, "date": datetime.datetime.now().isoformat(timespec="seconds")},
           "pieces": sum(len(r["pieces"]) for r in rows),
           "before": {k: tot("before", k) for k in ("wrong_slot", "child_for_adult", "mixed_gender_outfit", "colour_missing", "colour_named")},
           "after": {k: tot("after", k) for k in ("wrong_slot", "child_for_adult", "mixed_gender_outfit", "colour_missing", "colour_named")},
           "requests_changed": sum(1 for r in rows if r["notes"])}
json.dump(summary, open("runs/checks-eval.summary.json", "w"), indent=2)
print(json.dumps(summary, indent=2))
