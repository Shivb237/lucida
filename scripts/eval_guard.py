"""Evaluate the content-safety guard (src/genkart/guard.py). No paid calls; the local Qwen3 model reviews only 'review' cases.
Reports: misses (unsafe let through), false refusals (safe blocked) on hand-written cases, and false refusals on every real shopper prompt.
Writes runs/guard.summary.json and runs/guard.jsonl.  Usage: .venv/bin/python scripts/eval_guard.py"""
import glob, json, sys, time
sys.path.insert(0, "src")
from genkart import guard

cases = [json.loads(l) for l in open("data/fixtures/guard_cases.jsonl")]
real = []
for fn in sorted(glob.glob("data/human_prompts*.txt")):
    for l in open(fn):
        l = l.strip()
        if l and not l.startswith("#"):
            real.append({"text": l, "expect": "allow", "kind": "real:" + (fn.split("human_prompts")[-1].removesuffix(".txt").strip("_") or "base")})
reviewer = guard.make_reviewer()
rows, t_llm = [], []
for c in cases + real:
    r = guard.rules(c["text"])
    if r.action == "review":
        t = time.time(); f = guard.check(c["text"], reviewer); t_llm.append(time.time() - t)
    else:
        f = r
    rows.append({**c, "rules": r.action, "rules_cat": r.category, "final": "allow" if f.allowed else "refuse", "final_cat": f.category})
with open("runs/guard.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")

def stats(sub, key):
    unsafe = [r for r in sub if r["expect"] == "refuse"]; safe = [r for r in sub if r["expect"] == "allow"]
    # rules layer: "review" is not a decision, so count it as allowed-pending (shown separately)
    miss = [r for r in unsafe if (r[key] == "allow" or (key == "rules" and r[key] == "review"))]
    false = [r for r in safe if r[key] == "refuse"]
    pending = [r for r in sub if key == "rules" and r[key] == "review"]
    return {"n_unsafe": len(unsafe), "missed": len(miss), "n_safe": len(safe), "falsely_refused": len(false), "sent_to_review": len(pending)}, miss, false
hand = [r for r in rows if not r["kind"].startswith("real")]; realr = [r for r in rows if r["kind"].startswith("real")]
out = {"hand_rules_only": stats(hand, "rules")[0], "hand_full": stats(hand, "final")[0], "real_rules_only": stats(realr, "rules")[0], "real_full": stats(realr, "final")[0],
       "model_review_seconds_mean": round(sum(t_llm) / len(t_llm), 2) if t_llm else None, "n_model_reviews": len(t_llm), "n_real_prompts": len(realr)}
json.dump(out, open("runs/guard.summary.json", "w"), indent=2)
print(json.dumps(out, indent=1))
_, miss, false = stats(hand, "final"); print("\nMISSED (unsafe allowed):"); [print("  ", r["kind"], "|", r["text"][:80]) for r in miss]
print("FALSELY REFUSED (hand-written):"); [print("  ", r["kind"], "|", r["text"][:80], "|", r["final_cat"]) for r in false]
_, _, fr = stats(realr, "final"); print("FALSELY REFUSED (real prompts):"); [print("  ", r["text"][:90], "|", r["final_cat"]) for r in fr]
_, mr, _ = stats(hand, "rules"); print("rules-only misses (incl. waiting for model):", len(mr))
