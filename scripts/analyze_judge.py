"""How far can the LLM judge be trusted? Compares judge ratings with the user's 141 human ratings (test set 4) and writes runs/judge-validate.summary.json.
Scores: good=2, okay=1, bad=0. Agreement = same word. Weighted kappa (linear) corrects for chance and for near-misses counting less. Bootstrap 95% CIs over options."""
import json, random, statistics as st, sys
sys.path.insert(0, "src")
from genkart.metrics import weighted_kappa
S = {"good": 2, "okay": 1, "bad": 0}
R = [json.loads(l) for l in open("runs/judge-validate.jsonl")]
ok = [r for r in R if r["judge"] in S and r["human"] in S]
bad = len(R) - len(ok)
def kappa_w(rows):  # linear-weighted kappa, now in genkart.metrics (same formula)
    return weighted_kappa([S[r["human"]] for r in rows], [S[r["judge"]] for r in rows])
def agree(rows): return sum(r["human"] == r["judge"] for r in rows) / len(rows)
rng = random.Random(0)
def boot(f, rows, B=3000):
    v = sorted(f(rng.choices(rows, k=len(rows))) for _ in range(B)); return [round(v[int(.025 * B)], 3), round(v[int(.975 * B)], 3)]
conf = {h: {j: sum(1 for r in ok if r["human"] == h and r["judge"] == j) for j in S} for h in S}
by = {}
for m in "ABC":
    sub = [r for r in ok if r["method"][0] == m] if False else [r for r in ok if r["method"] == m]
    by[m] = {"n": len(sub), "human_mean": round(st.mean(S[r["human"]] for r in sub), 2), "judge_mean": round(st.mean(S[r["judge"]] for r in sub), 2)} if sub else None
out = {"n_options": len(R), "n_usable": len(ok), "unparsed": bad, "agreement": round(agree(ok), 3), "agreement_ci95": boot(agree, ok),
       "weighted_kappa": round(kappa_w(ok), 3), "kappa_ci95": boot(kappa_w, ok), "confusion_human_rows_judge_cols": conf,
       "human_mean": round(st.mean(S[r["human"]] for r in ok), 3), "judge_mean": round(st.mean(S[r["judge"]] for r in ok), 3),
       "judge_stricter_share": round(sum(S[r["judge"]] < S[r["human"]] for r in ok) / len(ok), 3), "judge_looser_share": round(sum(S[r["judge"]] > S[r["human"]] for r in ok) / len(ok), 3),
       "by_method": by, "note": "method 'A'/'B'/'C' = first method listed for the option in the key (options shared by several methods count once)"}
json.dump(out, open("runs/judge-validate.summary.json", "w"), indent=2); print(json.dumps(out, indent=1))
