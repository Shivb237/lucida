"""Milestone 4: score prompt v1 vs v2 on the user's held-out prompts with a fixed checklist (no answer labels exist for these).

The checklist below was written BEFORE running the model on these prompts. It is mechanical: no model judges another model.
Prompts and per-prompt plans stay in data/ (the user's own text, not in git); only counts go to runs/m4-heldout.summary.json.
Usage: .venv/bin/python scripts/eval_heldout.py
"""
import datetime
import json
import re
import sys

sys.path.insert(0, "src")
from genkart.understand import make_chain, understand  # noqa: E402

PROMPTS = [l.strip() for l in open("data/human_prompts_heldout.txt") if l.strip() and not l.startswith("#")]
assert len(PROMPTS) == 30, len(PROMPTS)

# Fixed before running. Index = prompt number - 1 in the file.
BUDGET = {1: 3000, 11: 5000, 25: 2500}          # prompts that state a budget; all others must give null
EXPECT_GENDER = {                                # acceptable genders; "unknown" is always fine when the prompt gives no cue
    1: {"men"}, 9: {"women"}, 10: {"men"}, 11: {"women"}, 12: {"girls"}, 13: {"men"}, 15: {"women"}, 16: {"men"}, 20: {"men"},
    22: {"women"}, 23: {"men"}, 24: {"men"}, 25: {"women"}, 27: {"women"}}
OPTIONAL_GENDER = {2, 5, 6, 7, 18, 19, 21, 26, 28, 29, 30}   # gender only implied: unknown or women both accepted
KEEP = {2: ["sundress"], 5: ["co-ord"], 7: ["kurti"], 9: ["lehenga"], 11: ["saree"], 12: ["dress"], 17: ["sweater", "jeans"],
        18: ["slip dress"], 21: ["cocktail dress"], 23: ["linen shirt", "trousers"], 25: ["gown"], 26: ["maxi dress"],
        27: ["leggings"], 28: ["dress"], 29: ["midi dress"], 30: ["gown"]}
COLOURS = {5: ["navy"], 9: ["yellow"], 12: ["red"], 13: ["black"], 18: ["emerald green"], 21: ["black"], 23: ["beige"], 28: ["dark red"], 30: ["red"]}
VAGUE = re.compile(r"\b(outfit|outfits|look|looks|vibe|ideas|idea|style|styles|attire)\b", re.IGNORECASE)


def norm(s):
    return re.sub(r"[\s\-]+", " ", s.lower()).replace("co ord", "coord")


def checks(n, plan):
    pieces = plan["pieces"]
    texts = norm(" ".join([plan["main_query"]] + [p["search_text"] for p in pieces]))
    out = {"not_empty": len(pieces) > 0,
           "no_vague_piece": not any(VAGUE.search(p["search_text"]) for p in pieces),
           "budget": (plan["budget_inr"] == BUDGET[n]) if n in BUDGET else plan["budget_inr"] is None}
    if n in EXPECT_GENDER:
        out["gender"] = plan["gender"] in EXPECT_GENDER[n] | {"unknown"}
        out["gender_stated_found"] = plan["gender"] in EXPECT_GENDER[n]
    elif n in OPTIONAL_GENDER:
        out["gender"] = plan["gender"] in {"unknown", "women"}
    else:
        out["gender"] = plan["gender"] == "unknown"
    if n in KEEP:
        out["product_kept"] = all(norm(k) in texts for k in KEEP[n])
    if n in COLOURS:
        out["colour_kept"] = all(norm(c) in texts for c in COLOURS[n])
    return out


chain = make_chain()
rows, tally = [], {}
for version in ("v1", "v2"):
    tally[version] = {}
    for n, text in enumerate(PROMPTS, 1):
        plan, secs = understand(text, chain, version=version)
        plan = plan.model_dump()
        c = checks(n, plan)
        rows.append({"n": n, "prompt": text, "version": version, "plan": plan, "seconds": round(secs, 2), "checks": c})
        for k, v in c.items():
            t = tally[version].setdefault(k, [0, 0])
            t[0] += int(v)
            t[1] += 1
with open("data/heldout_rows.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
summary = {"date": datetime.datetime.now().isoformat(timespec="seconds"), "n_prompts": len(PROMPTS), "model": "qwen3:4b-instruct via langchain-ollama",
           "checks_passed": {v: {k: f"{a}/{b}" for k, (a, b) in t.items()} for v, t in tally.items()}}
json.dump(summary, open("runs/m4-heldout.summary.json", "w"), indent=2)
print(f"{'check':22} {'v1':>8} {'v2':>8}")
for k in tally["v1"]:
    print(f"{k:22} {tally['v1'][k][0]:>4}/{tally['v1'][k][1]:<3} {tally['v2'][k][0]:>4}/{tally['v2'][k][1]:<3}")
