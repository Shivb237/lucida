"""Write REPORT.md from runs/*.summary.json. Every number is read from a file, none is typed here.
Same verdict rule as the Evidence page (web/vite.config.ts): helped / no clear effect / hurt, from whether the 95% range excludes zero.
Usage: .venv/bin/python scripts/make_report.py [--out REPORT.md] [--runs runs]   (offline, deterministic, no timestamps)"""
import argparse, json, math, pathlib

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="REPORT.md")
ap.add_argument("--runs", default="runs")
args = ap.parse_args()
RUNS = pathlib.Path(args.runs)


def J(name):
    return json.load(open(RUNS / name))


def JL(name):
    return [json.loads(l) for l in open(RUNS / name) if l.strip()]


def sg(x, d=3):
    t = f"{(0.0 if abs(x) < 0.5 * 10 ** -d else x):.{d}f}"
    return t if t.startswith("-") else f"+{t}"


def fx(x, d=3):
    return f"{x:.{d}f}"


def rng(ci, d=3):
    return f"{sg(ci[0], d)} to {sg(ci[1], d)}"


def verdict(ci, higher_is_better=True, ref=0.0):
    if ci[0] > ref:
        return "helped" if higher_is_better else "hurt"
    if ci[1] < ref:
        return "hurt" if higher_is_better else "helped"
    return "no clear effect"


def sign_p(better, worse):
    m = better + worse
    if not m:
        return 1.0
    tail = sum(math.comb(m, k) for k in range(min(better, worse) + 1)) / 2 ** m
    return min(1.0, 2 * tail)


def wilson(k, n):
    z = 1.959964
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def eff(p, d=3):
    """A paired block {mean, ci95, ...} -> 'verdict: +mean (95% range a to b)'."""
    return f"{verdict(p['ci95'])}: {sg(p['mean'], d)} (95% range {rng(p['ci95'], d)})"


# ---- read the files -----------------------------------------------------------------------------------------------
ep = {p["id"]: p for p in J("evidence-paired.summary.json")["pairs"]}
m2 = J("m2.summary.json")
b3, b4, b5 = J("blind-test3.summary.json"), J("blind-test4.summary.json"), J("blind-test5.summary.json")
g = J("graph-holdout.summary.json")
col = J("outfit-ratings.summary.json")
fb = J("feedback-sim.summary.json")["metrics"]["likes_only"]
jv, j5 = J("judge-validate.summary.json"), J("judge-test5.summary.json")
ce = J("checks-eval.summary.json")
ce_rows = JL("checks-eval.jsonl")
gd = J("guard.summary.json")
dq, du = J("data-quality-4.summary.json"), J("duplicates.summary.json")
big = J("scale-marqo-fashionsiglip.summary.json")["metrics"]["ndcg10"]
fo, ov = J("aws-failover.summary.json"), J("aws-overload-experiment.summary.json")

# checks: sign test over requests, as the Evidence page does
BREAKS = ("wrong_slot", "child_for_adult", "mixed_gender_outfit", "colour_missing")
d = [sum(r["after"][k] for k in BREAKS) - sum(r["before"][k] for k in BREAKS) for r in ce_rows]
better, worse, tied = sum(x < 0 for x in d), sum(x > 0 for x in d), sum(x == 0 for x in d)
ck_verdict = "helped" if sign_p(better, worse) < 0.05 and better > worse else ("hurt" if sign_p(better, worse) < 0.05 else "no clear effect")
ck_before, ck_after = sum(ce["before"][k] for k in BREAKS), sum(ce["after"][k] for k in BREAKS)

hf, rf = gd["hand_full"], gd["real_full"]
caught = hf["n_unsafe"] - hf["missed"]
gci = wilson(caught, hf["n_unsafe"])
g_verdict = verdict(gci)

agree = [p for p in sorted(RUNS.glob("blind-test*-agreement.summary.json"))]
if agree:
    raters_note = "A second rater exists. Agreement files: " + ", ".join(p.name for p in agree) + ". See them for the agreement scores."
else:
    raters_note = "One human rater did all blind ratings, and the same person wrote the prompts. No second rater yet."

ov_v2, ov_base = ov["variants"]["v2"]["hardest_level"], ov["variants"]["baseline"]["hardest_level"]
sizes = dq["sizes"]
M2N = {"gen-resnet50": "Drawing, general image model", "gen-fashionsiglip": "Drawing, fashion model", "text+gen-fashionsiglip": "Words plus drawing, fashion model"}

rows = [
    ("Search model", "Fashion model minus general model (bigger test)", eff(ep["scale-marqo-vs-siglip"]["metrics"]["ndcg10"]), ep["scale-marqo-vs-siglip"]["n"], "evidence-paired.summary.json"),
    ("Search model", "Fashion model minus keyword search BM25 (bigger test)", eff(ep["scale-marqo-vs-bm25"]["metrics"]["ndcg10"]), ep["scale-marqo-vs-bm25"]["n"], "evidence-paired.summary.json"),
]
for k in ("gen-resnet50", "gen-fashionsiglip", "text+gen-fashionsiglip"):
    rows.append(("Draw first", f"{M2N[k]} minus typed words", eff(m2["paired_vs_direct_text"][k]["ndcg10"]), m2["setup"]["n_queries"], "m2.summary.json"))
rows += [
    ("Collections", "Four collections minus one (test 4, raw words)", eff(b4["paired"]["B-A"], 2), b4["methods"]["A"]["n_prompts"], "blind-test4.summary.json"),
    ("Plan vs plain search", "AI plan minus raw words (test 3, one collection)", eff(b3["paired"]["plan-raw"], 2), b3["paired"]["plan-raw"]["n_prompts"], "blind-test3.summary.json"),
    ("Plan vs plain search", "AI plan minus raw words (test 4)", eff(b4["paired"]["C-B"], 2), b4["methods"]["B"]["n_prompts"], "blind-test4.summary.json"),
    ("Plan vs plain search", "Local AI plan minus raw words (test 5)", eff(b5["C_minus_B"], 2), b5["n_prompts"], "blind-test5.summary.json"),
    ("Plan vs plain search", "Claude plan minus raw words (test 5)", eff(b5["D_minus_B"], 2), b5["n_prompts"], "blind-test5.summary.json"),
    ("Clothes map", "With map minus without, right type in top 3", f"{verdict(g['overall']['ci95'])}: {sg(g['overall']['difference'])} (95% range {rng(g['overall']['ci95'])})", g["n_test"], "graph-holdout.summary.json"),
    ("Colour check", "Chosen for harmony minus best match (blind)", eff(col["paired"]["coherent-baseline"], 2), col["paired"]["coherent-baseline"]["n_prompts"], "outfit-ratings.summary.json"),
    ("Likes", "With likes minus without (simulated shopper)", eff(fb["paired_difference"]), fb["n_test_queries"], "feedback-sim.summary.json"),
    ("AI judge", "Judge vs person, test 4, weighted kappa", f"kappa {fx(jv['weighted_kappa'])} (95% range {fx(jv['kappa_ci95'][0])} to {fx(jv['kappa_ci95'][1])}); same rating on {jv['agreement']:.1%}", jv["n_usable"], "judge-validate.summary.json"),
    ("AI judge", "Judge vs person, test 5, weighted kappa", f"kappa {fx(j5['weighted_kappa'])} (95% range {fx(j5['kappa_ci95'][0])} to {fx(j5['kappa_ci95'][1])}); same rating on {j5['agreement']:.1%}", j5["n_options"], "judge-test5.summary.json"),
    ("Rule checks", "Rule breaks in first picks, after minus before", f"{ck_verdict}: {ck_before} breaks fell to {ck_after}; {better} requests better, {worse} worse, {tied} same (sign test)", len(ce_rows), "checks-eval.summary.json"),
    ("Safety guard", "Unsafe test prompts stopped", f"{g_verdict}: {caught} of {hf['n_unsafe']} (95% range {gci[0]:.3f} to {gci[1]:.3f})", hf["n_unsafe"], "guard.summary.json"),
    ("Safety guard", "Safe prompts wrongly refused", f"{hf['falsely_refused']} of {hf['n_safe']} hand-written; {rf['falsely_refused']} of {rf['n_safe']} real requests", hf["n_safe"] + rf["n_safe"], "guard.summary.json"),
    ("Data quality", "Fashion model minus general model, near-copies merged", eff({"mean": du["rescoring_pairs"]["marqo-fashionsiglip - siglip-base"]["ded"][0], "ci95": du["rescoring_pairs"]["marqo-fashionsiglip - siglip-base"]["ded"][1:]}), ep["scale-marqo-vs-siglip"]["n"], "duplicates.summary.json"),
    ("Data quality", "Near-copy products across four collections", f"{dq['products_in_clusters']:,} of {dq['total']:,} ({dq['products_in_clusters'] / dq['total']:.1%})", dq["total"], "data-quality-4.summary.json"),
    ("Serving", "Searches with a shard machine switched off", f"{fo['totals']['errors']} errors in {fo['totals']['searches']} searches", fo["totals"]["searches"], "aws-failover.summary.json"),
    ("Serving", "Overload at 32 requests in flight (new vs old router)", f"{ov_v2['shed']} of {ov_v2['requests']} shed in a median {ov_v2['shed_p50_ms']} ms; old router: {ov_base['errors']} errors of {ov_base['requests']}", ov_v2["requests"], "aws-overload-experiment.summary.json"),
]
table = "\n".join(["| Claim | Comparison | Result (95% range) | n | Source file |", "|---|---|---|---|---|"] +
                  [f"| {a} | {b} | {c} | {n:,} | runs/{s} |" for a, b, c, n, s in rows])

T = f"""# Lucida: two-page report

Generated from the run files in `runs/`. Do not edit by hand.

## 1. Question and why

A shopper describes an occasion. The system returns a whole outfit, not one item.
Version 1 drew the outfit with an image model first, then searched with the drawing.
The question: does drawing first help? We also tested the other steps.

## 2. The system in one paragraph

A request passes six steps: request (with a safety check), read your sentence, add missing ideas, find products, pick an outfit, show the outfit.
Search covers four product collections, about {dq['unique_after_merge']:,} products after removing near-copies ({dq['total']:,} before).
A small reading model (Qwen3, 4 billion parameters) runs locally. It turns the sentence into a plan.
A router sends each search to shards, which are slices of the product index. It merges the answers.
Search uses the Marqo fashion model. It puts words and pictures in one space.

## 3. How it was measured

- Search labels come from shopping rankings. A product is relevant if the shop ranked it for the query.
- Outfits were rated blind by a person: 2 is good, 1 is okay, 0 is bad. The rater did not see the method.
- Differences are paired: the same request is compared across methods. Ranges are 95% bootstrap ranges (resampled requests).
- Search quality is nDCG@10, a 0-to-1 score for ranking the right products near the top.
- Verdict rule: "helped" or "hurt" when the 95% range excludes zero. Otherwise "no clear effect".
- Test 3 was used to find and fix bugs, so it is no longer a fair test. Tests 4 and 5 were each rated once for their comparison; changes made after seeing them would need a new test set.

## 4. Results

{table}

Verdict words follow the rule in section 3. Rule checks use a sign test over requests, since that file has counts, not ranges.

## 5. Limits

- {raters_note}
- Test sets are used up. Rerunning them after changes would no longer be a fair test.
- Search labels come from a text-query shopping ranking. Text search is built into the labels, so it starts ahead.
- The drawing prompt is a fixed template, with no rewrite and one random seed per query.
- The drawing test used only {m2['setup']['n_queries']} queries on the small catalogue of {m2['setup']['n_products']:,} products. Its ranges are wide.
- Scores on different catalogues are not comparable. Direct text scores {fx(m2['metrics']['direct-text']['ndcg10']['mean'])} there, but the fashion model scores {fx(big['mean'])} on the bigger test.
- All data is public. There are no real users and no study results.
- The AWS machines were torn down on 2026-10-16. Serving numbers are recordings, not live tests.

## 6. What I would do next

- Run a bigger drawing test, with a request-rewrite arm, on the full catalogue.
- Add more raters, so agreement between people can be measured.
- Run a hosted study with frozen stimuli, so every participant sees the same items.

Every number above is read from runs/*.summary.json by scripts/make_report.py.
"""
pathlib.Path(args.out).write_text(T, encoding="utf-8")
print(f"wrote {args.out} ({len(T.split())} words)")
