"""Test set 5 results: per-method mean rating (good=2, okay=1, bad=0) from the user's blind ratings, paired by prompt, bootstrap 95% CIs over prompts.
Options shared by several methods give the same rating to each. Writes runs/blind-test5.summary.json."""
import json, random, statistics as st
S = {"good": 2, "okay": 1, "bad": 0}
key = json.load(open("data/preview/blind_key5.json")); h = json.load(open("data/human_ratings_test5.json"))
per = {n: {} for n in range(1, 51)}
for k, methods in key.items():
    n = int(k.split("-")[0][1:])
    for m in methods: per[n][m] = S[h[k]]
rng = random.Random(0)
def ci(xs, B=5000):
    v = sorted(st.mean(rng.choices(xs, k=len(xs))) for _ in range(B)); return [round(v[int(.025 * B)], 3), round(v[int(.975 * B)], 3)]
out = {"n_prompts": 50, "n_ratings": len(h)}
out["mean"] = {m: round(st.mean(per[n][m] for n in per), 3) for m in "BCD"}
out["share_good"] = {m: round(sum(per[n][m] == 2 for n in per) / 50, 3) for m in "BCD"}
out["share_bad"] = {m: round(sum(per[n][m] == 0 for n in per) / 50, 3) for m in "BCD"}
for a, b in (("C", "B"), ("D", "B"), ("D", "C")):
    d = [per[n][a] - per[n][b] for n in per]
    out[f"{a}_minus_{b}"] = {"mean": round(st.mean(d), 3), "ci95": ci(d), "better": sum(x > 0 for x in d), "worse": sum(x < 0 for x in d), "equal": sum(x == 0 for x in d)}
json.dump(out, open("runs/blind-test5.summary.json", "w"), indent=2); print(json.dumps(out, indent=1))
