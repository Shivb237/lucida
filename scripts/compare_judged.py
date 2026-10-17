"""Paired comparison of Qwen3-plan options (C) vs Claude-plan options (D) on test set 4 using the LLM judge (validated: see runs/judge-validate.summary.json).
Both are multi-row outfit options, so the judge's known bias against outfits (it scored outfits lower than the human did) should affect both alike.
Also shows the human ratings for C where options C were identical to B etc. Writes runs/claude-vs-qwen-judged.summary.json."""
import json, random, statistics as st
S = {"good": 2, "okay": 1, "bad": 0}
key = json.load(open("data/preview/blind_key4.json"))
val = {r["id"]: r for r in map(json.loads, open("runs/judge-validate.jsonl"))}
D = {r["n"]: r for r in map(json.loads, open("runs/judge-claude.jsonl"))}
c_id = {}
for k, v in key.items():
    if "C" in v: c_id[int(k.split("-")[0][1:])] = k
rows = []
for n in range(1, 51):
    c, d = val[c_id[n]], D[n]
    if c["judge"] in S and d["judge"] in S:
        rows.append({"n": n, "qwen": S[c["judge"]], "claude": S[d["judge"]], "same_photos": c["rows"] == d["rows"], "human_c": c["human"]})
diff = [r["claude"] - r["qwen"] for r in rows]; rng = random.Random(0)
bs = sorted(st.mean(rng.choices(diff, k=len(diff))) for _ in range(5000))
diff_only = [r["claude"] - r["qwen"] for r in rows if not r["same_photos"]]
out = {"n": len(rows), "judge_mean_qwen_plans": round(st.mean(r["qwen"] for r in rows), 3), "judge_mean_claude_plans": round(st.mean(r["claude"] for r in rows), 3),
       "diff_claude_minus_qwen": round(st.mean(diff), 3), "diff_ci95": [round(bs[125], 3), round(bs[4874], 3)],
       "prompts_with_identical_photos": sum(r["same_photos"] for r in rows), "prompts_claude_better": sum(x > 0 for x in diff), "prompts_qwen_better": sum(x < 0 for x in diff),
       "mean_diff_only_where_photos_differ": round(st.mean(diff_only), 3) if diff_only else None, "n_where_photos_differ": len(diff_only)}
json.dump(out, open("runs/claude-vs-qwen-judged.summary.json", "w"), indent=2); print(json.dumps(out, indent=1))
for r in rows:
    if r["claude"] != r["qwen"]: print(f"  #{r['n']} qwen {r['qwen']} claude {r['claude']} (human on qwen option: {r['human_c']})")
