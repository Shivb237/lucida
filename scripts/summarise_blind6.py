"""Test set 6 results: with vs without the tiny Kaggle small photos, from the user's blind ratings (good=2, okay=1, bad=0).
Only prompts whose two options differed were rated; prompts with identical results count as ties (difference 0) in the 60-prompt figure.
Writes runs/blind-test6.summary.json. Usage: .venv/bin/python scripts/summarise_blind6.py   (needs data/human_ratings_test6.json)"""
import json
import random
import statistics as st

S = {"good": 2, "okay": 1, "bad": 0}
key = json.load(open("data/preview/blind_key6.json"))
h = json.load(open("data/human_ratings_test6.json"))
per = {}
for k, (method,) in key.items():
    per.setdefault(int(k.split("-")[0][1:]), {})[method] = S[h[k]]
d = [v["B_no_tiny"] - v["A_all"] for v in per.values()]          # positive = removing the tiny photos looks better
rng = random.Random(0)


def ci(xs, n=5000):
    v = sorted(st.mean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return [round(v[int(.025 * n)], 3), round(v[int(.975 * n)], 3)]


out = {"prompts_total": 60, "prompts_rated": len(per), "prompts_identical": 60 - len(per),
       "mean_with_tiny": round(st.mean(v["A_all"] for v in per.values()), 3), "mean_without_tiny": round(st.mean(v["B_no_tiny"] for v in per.values()), 3),
       "without_minus_with_among_rated": {"mean": round(st.mean(d), 3), "ci95": ci(d), "better": sum(x > 0 for x in d), "worse": sum(x < 0 for x in d), "equal": sum(x == 0 for x in d)}}
d60 = d + [0] * (60 - len(d))
out["without_minus_with_all_60"] = {"mean": round(st.mean(d60), 3), "ci95": ci(d60)}
json.dump(out, open("runs/blind-test6.summary.json", "w"), indent=2)
print(json.dumps(out, indent=1))
