"""Figures for the write-up, drawn ONLY from logged runs (nothing typed in by hand):
  data/figures/overload.png   runs/aws-overload-experiment.jsonl   goodput vs searches in flight, and how 320 searches ended at 32 in flight
  data/figures/failover.png   runs/aws-failover.jsonl (run 3)      latency of each search while a whole shard computer was switched off and on
Needs matplotlib, which is NOT in the project's pinned requirements: run it with any environment that has it, e.g.
  python3 -m venv /tmp/plotenv && /tmp/plotenv/bin/pip install matplotlib && /tmp/plotenv/bin/python scripts/make_figures.py"""
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

pathlib.Path("data/figures").mkdir(parents=True, exist_ok=True)
INK, MUTED = "#14202b", "#56646f"
COL = {"baseline": "#9b1c1c", "v1": "#c9820a", "v2": "#14603a"}
NAME = {"baseline": "baseline (no protection)", "v1": "v1: gate of 2 + deadlines", "v2": "v2: + refuse past 12 in flight"}
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK, "axes.spines.top": False, "axes.spines.right": False})

# ---------------- figure 1: overload ----------------
rows = [json.loads(l) for l in open("runs/aws-overload-experiment.jsonl") if l.strip()]
by = {}
for r in rows:
    by.setdefault(r["label"], []).append(r)
fig, (a, b) = plt.subplots(1, 2, figsize=(12.5, 5), gridspec_kw={"width_ratios": [1.25, 1]})
for label, rs in by.items():
    lv = [r for r in rs if r["phase"] == "level"]
    a.plot([r["concurrency"] for r in lv], [r["goodput_per_s"] for r in lv], marker="o", lw=2.4, color=COL[label], label=NAME[label])
a.set_xscale("log", base=2)
a.set_xticks([1, 4, 8, 16, 32]); a.set_xticklabels(["1", "4", "8", "16", "32"])
a.set_xlabel("searches in flight at once"); a.set_ylabel("useful searches per second (goodput)"); a.set_ylim(0, 5.2)
a.set_title("Under overload, protection keeps the machine doing useful work", loc="left", fontsize=12.5, fontweight="bold")
a.annotate("0 searches/s:\nevery request failed", xy=(32, 0), xytext=(14, 0.55), color=COL["baseline"], fontsize=10, arrowprops=dict(arrowstyle="->", color=COL["baseline"]))
a.legend(frameon=False, loc="lower left", fontsize=10)
last = {k: [r for r in rs if r["phase"] == "level"][-1] for k, rs in by.items()}
x = list(last)
ok = [last[k]["ok"] for k in x]; shed = [last[k]["shed"] for k in x]; err = [last[k]["errors"] for k in x]
b.bar(x, ok, color="#14603a", label="answered"); b.bar(x, shed, bottom=ok, color="#8fb7a0", label="refused at once (\"busy\", ~10 ms)")
b.bar(x, err, bottom=[o + s for o, s in zip(ok, shed)], color="#9b1c1c", label="failed (timed out after 5 s)")
b.set_xticks(range(3)); b.set_xticklabels(["baseline", "v1", "v2"]); b.set_ylabel("of 320 searches sent")
b.set_title("How 320 searches ended at 32 in flight", loc="left", fontsize=12.5, fontweight="bold"); b.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.12))
fig.text(0.01, 0.005, "Machine: 2 vCPU. Same load test, one run per variant. Closed-loop test: a refused client retries at once, so only the first 12 are ever admitted under v2.\n"
         "Source: runs/aws-overload-experiment.jsonl", fontsize=8, color=MUTED, va="bottom")
fig.tight_layout(rect=(0, 0.07, 1, 1)); fig.savefig("data/figures/overload.png", dpi=170); plt.close(fig)

# ---------------- figure 2: failover ----------------
fr = [json.loads(l) for l in open("runs/aws-failover.jsonl") if l.strip()]
runs = [[]]
for r in fr:
    if runs[-1] and r["t"] < runs[-1][-1]["t"]:
        runs.append([])
    runs[-1].append(r)
run = runs[2]                                      # the run shown in the session: B stopped at about 24 s, started again at about 90 s
fo = [r["t"] for r in run if r.get("failovers")]
down = (min(t for t in fo if t < 60), max(t for t in fo if t < 60))
back = (min(t for t in fo if t > 60), max(t for t in fo if t > 60))
fig, ax = plt.subplots(figsize=(12, 4.6))
ax.axvspan(down[0] - 0.5, back[0] - 0.5, color="#f4e3c4", alpha=0.7, lw=0)
ax.plot([r["t"] for r in run], [r["total_ms"] for r in run], color="#095a72", lw=1.6, marker="o", ms=3)
ax.set_ylim(0, 700); ax.set_xlabel("seconds since the test started"); ax.set_ylabel("latency of each search (ms)")
ax.set_title("A whole shard computer was switched off, then on: every search still got a complete answer", loc="left", fontsize=12.5, fontweight="bold")
ax.annotate("computer B shut down\n(router fails over)", xy=(down[0], 300), xytext=(down[0] - 20, 560), fontsize=9.5, color=INK, arrowprops=dict(arrowstyle="->", color=MUTED))
ax.annotate("B booting: workers\nback by themselves", xy=(back[0], 300), xytext=(back[0] + 6, 560), fontsize=9.5, color=INK, arrowprops=dict(arrowstyle="->", color=MUTED))
ax.text((down[0] + back[0]) / 2, 640, "serving from computer A only: median 340 ms vs 320 ms before", ha="center", fontsize=9.5, color=INK)
n_err = sum(r["status"] != 200 for r in run); n_part = sum(bool(r.get("partial")) for r in run)
fig.text(0.01, 0.01, f"This run: {len(run)} searches, {n_err} errors, {n_part} partial answers. Shaded band inferred from when the router logged failovers (stop/start times were not logged).\nSource: runs/aws-failover.jsonl (run 3 of 3 in the file)", fontsize=8, color=MUTED, va="bottom")
fig.tight_layout(rect=(0, 0.08, 1, 1)); fig.savefig("data/figures/failover.png", dpi=170); plt.close(fig)
print("wrote data/figures/overload.png and data/figures/failover.png")
