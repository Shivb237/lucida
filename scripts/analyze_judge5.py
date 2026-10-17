"""Judge vs human on test set 5 (options the judge never saw before; the judge setup was fixed before these ratings existed).
Agreement, weighted kappa, confusion, and whether the judge's method comparisons (C-B, D-B, D-C, paired by prompt) match the human's. Writes runs/judge-test5.summary.json."""
import collections, json, random, statistics as st
S = {"good": 2, "okay": 1, "bad": 0}
R = [json.loads(l) for l in open("runs/judge-test5.jsonl")]
key = json.load(open("data/preview/blind_key5.json"))
ok = [r for r in R if r["judge"] in S and r["human"] in S]
def kw(rows):
    n = len(rows); O = collections.Counter((S[r["human"]], S[r["judge"]]) for r in rows)
    ph = collections.Counter(S[r["human"]] for r in rows); pj = collections.Counter(S[r["judge"]] for r in rows)
    num = sum(abs(i - j) * O[(i, j)] / n for i in range(3) for j in range(3)); den = sum(abs(i - j) * ph[i] * pj[j] / n / n for i in range(3) for j in range(3))
    return 1 - num / den if den else float("nan")
ag = lambda rows: sum(r["human"] == r["judge"] for r in rows) / len(rows)
rng = random.Random(0)
def boot(f, rows, B=3000):
    v = sorted(f(rng.choices(rows, k=len(rows))) for _ in range(B)); return [round(v[int(.025 * B)], 3), round(v[int(.975 * B)], 3)]
out = {"n_options": len(R), "unparsed": len(R) - len(ok), "agreement": round(ag(ok), 3), "agreement_ci95": boot(ag, ok), "weighted_kappa": round(kw(ok), 3), "kappa_ci95": boot(kw, ok),
       "confusion_human_rows_judge_cols": {h: {j: sum(1 for r in ok if r["human"] == h and r["judge"] == j) for j in S} for h in S},
       "human_mean": round(st.mean(S[r["human"]] for r in ok), 3), "judge_mean": round(st.mean(S[r["judge"]] for r in ok), 3)}
jid = {r["id"]: r for r in ok}
per_h, per_j = {n: {} for n in range(1, 51)}, {n: {} for n in range(1, 51)}
for k, methods in key.items():
    n = int(k.split("-")[0][1:])
    if k in jid:
        for m in methods: per_h[n][m] = S[jid[k]["human"]]; per_j[n][m] = S[jid[k]["judge"]]
cmp = {}
for a, b in (("C", "B"), ("D", "B"), ("D", "C")):
    ns = [n for n in per_h if a in per_h[n] and b in per_h[n]]
    dh = [per_h[n][a] - per_h[n][b] for n in ns]; dj = [per_j[n][a] - per_j[n][b] for n in ns]
    cmp[f"{a}-{b}"] = {"n": len(ns), "human_mean_diff": round(st.mean(dh), 3), "judge_mean_diff": round(st.mean(dj), 3), "judge_ci95": boot(lambda x: st.mean(x), dj)}
out["method_comparisons"] = cmp
out["by_method_mean"] = {m: {"human": round(st.mean(per_h[n][m] for n in per_h if m in per_h[n]), 3), "judge": round(st.mean(per_j[n][m] for n in per_j if m in per_j[n]), 3)} for m in "BCD"}
json.dump(out, open("runs/judge-test5.summary.json", "w"), indent=2); print(json.dumps(out, indent=1))
