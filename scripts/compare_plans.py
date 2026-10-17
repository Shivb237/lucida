"""Claude vs local Qwen3 plans on test set 4 (50 prompts): checkable properties only (no relevance labels exist for these plans).
word_kept = share of the shopper's content words (>=4 letters, not filler) that appear in some piece's search_text.  Writes runs/claude-vs-qwen.summary.json."""
import json, re, statistics as st, random
STOP = set("with that this have your from what want need looking look outfit wear wearing something some like also good best nice please for the and my our his her their day".split())
q = {json.loads(l)["n"]: json.loads(l) for l in open("data/test4_plans.jsonl")}
c = {json.loads(l)["n"]: json.loads(l) for l in open("runs/claude-plans.jsonl")}
def words(t): return {w for w in re.findall(r"[a-z]+", t.lower()) if len(w) >= 4 and w not in STOP}
def kept(prompt, plan):
    w = words(prompt); txt = " ".join(p["search_text"] for p in plan["pieces"]).lower()
    return sum(x in txt for x in w) / max(1, len(w)), [x for x in w if x not in txt]
rows = []
for n in sorted(q):
    pq, pc = q[n]["plan"], c[n]["plan"]
    kq, lq = kept(q[n]["prompt"], pq); kc, lc = kept(q[n]["prompt"], pc)
    rows.append({"n": n, "prompt": q[n]["prompt"], "kept_qwen": kq, "kept_claude": kc, "lost_qwen": lq, "lost_claude": lc, "pieces_qwen": len(pq["pieces"]), "pieces_claude": len(pc["pieces"]),
                 "gender_same": pq["gender"] == pc["gender"], "qwen_q": [p["search_text"] for p in pq["pieces"]], "claude_q": [p["search_text"] for p in pc["pieces"]]})
d = [r["kept_claude"] - r["kept_qwen"] for r in rows]
rng = random.Random(0); bs = sorted(st.mean(rng.choices(d, k=len(d))) for _ in range(5000))
out = {"n": len(rows), "word_kept_qwen": round(st.mean(r["kept_qwen"] for r in rows), 3), "word_kept_claude": round(st.mean(r["kept_claude"] for r in rows), 3),
       "diff_claude_minus_qwen": round(st.mean(d), 3), "diff_ci95": [round(bs[125], 3), round(bs[4874], 3)],
       "pieces_mean_qwen": round(st.mean(r["pieces_qwen"] for r in rows), 2), "pieces_mean_claude": round(st.mean(r["pieces_claude"] for r in rows), 2),
       "gender_agree": sum(r["gender_same"] for r in rows), "claude_plans_valid": sum(c[n]["ok"] for n in c),
       "claude_cost_usd": round(sum(json.loads(l)["cost_usd"] for l in open("runs/claude-spend.jsonl")), 4)}
json.dump(out, open("runs/claude-vs-qwen.summary.json", "w"), indent=2); json.dump(rows, open("runs/claude-vs-qwen.rows.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1))
print("\nwhere Claude kept more of the shopper's words (first 6):")
for r in sorted(rows, key=lambda r: r["kept_qwen"] - r["kept_claude"])[:6]:
    print(f"  #{r['n']} {r['prompt'][:70]}\n     qwen {r['qwen_q']} lost {r['lost_qwen']}\n     claude {r['claude_q']} lost {r['lost_claude']}")
print("\nwhere Qwen kept more (first 4):")
for r in sorted(rows, key=lambda r: r["kept_claude"] - r["kept_qwen"])[:4]:
    print(f"  #{r['n']} {r['prompt'][:70]}\n     qwen {r['qwen_q']} lost {r['lost_qwen']}\n     claude {r['claude_q']} lost {r['lost_claude']}")
