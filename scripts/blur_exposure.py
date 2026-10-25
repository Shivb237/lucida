"""How often does a shopper SEE a tiny photo? Counts which catalogue each shown result comes from.

Runs the real search (all four catalogues, same fallback rule as the site) for the 100 prompts of test sets 4 and 5, once with the sentence as typed
and once with the Qwen3 plan's pieces (the saved plans), and counts the source of every one of the top 6 results.
Kaggle small photos are all 60 x 80 pixels (measured: longest side 80 at p5, p50 and p95), so a Kaggle result is always shown tiny.
Usage: .venv/bin/python scripts/blur_exposure.py [--drop-kaggle]     -> runs/blur-exposure[-no-kaggle].jsonl + .summary.json
--drop-kaggle searches WITHOUT the Kaggle small catalogue, to see what its removal would change (top-1 score and who answers instead).
"""
import collections
import json
import pathlib
import sys

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402

TOP = 6
DROP = "--drop-kaggle" in sys.argv
TAG = "-no-kaggle" if DROP else ""
model, _pre, tok, dev = embed.load("marqo-fashionsiglip")
cat = Catalogue.load()
if DROP:
    cat.specialists = [s for s in cat.specialists if s.name != "kaggle"]
rows, out = [], pathlib.Path("runs")
for test in (4, 5):
    prompts = [l.strip() for l in open(f"data/human_prompts_test{test}.txt") if l.strip() and not l.startswith("#")]
    plans = [json.loads(l) for l in open(f"data/test{test}_plans.jsonl")]
    for n, p in enumerate(prompts[:50], 1):
        items = [("sentence", p, None)]
        plan = (plans[n - 1].get("plan") or plans[n - 1].get("qwen")) if n <= len(plans) else None   # test 4 files store "plan", test 5 stores "qwen"
        if plan:
            g = plan.get("gender")
            items += [("plan_piece", pc["search_text"], g) for pc in plan.get("pieces", [])]
        for mode, text, g in items:
            v = embed.encode_texts(model, tok, [text], dev)[0]
            hits = cat.search(v, k=TOP, gender=g if g in ("men", "women", "boys", "girls", "unisex") else None)
            rows.append({"test": test, "n": n, "mode": mode, "text": text, "sources": [h.source for h in hits], "top1": round(hits[0].score, 4) if hits else None})
with open(out / f"blur-exposure{TAG}.jsonl", "w") as f:
    f.writelines(json.dumps(r) + "\n" for r in rows)
summary = {"top": TOP, "searches": len(rows), "by_mode": {}}
for mode in ("sentence", "plan_piece"):
    rs = [r for r in rows if r["mode"] == mode]
    c = collections.Counter(s for r in rs for s in r["sources"])
    total = sum(c.values())
    summary["by_mode"][mode] = {
        "searches": len(rs), "results_shown": total,
        "share_by_source": {k: round(v / total, 4) for k, v in c.most_common()},
        "searches_with_any_kaggle_small": round(sum("kaggle" in r["sources"] for r in rs) / len(rs), 4),
        "mean_top1_score": round(sum(r["top1"] or 0 for r in rs) / len(rs), 4),
        "searches_with_no_result": sum(not r["sources"] for r in rs),
        "searches_with_only_kaggle_small": round(sum(set(r["sources"]) == {"kaggle"} for r in rs) / len(rs), 4),
    }
(out / f"blur-exposure{TAG}.summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
