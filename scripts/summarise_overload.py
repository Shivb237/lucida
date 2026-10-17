"""Summarise runs/aws-overload-experiment.jsonl (written by scripts/aws_loadtest.py via scripts/run_variant.sh): one table per variant, a side-by-side view
of the hardest level and the recovery rows, and runs/aws-overload-experiment.summary.json. Reads only the logged records."""
import json
import collections

rows = [json.loads(l) for l in open("runs/aws-overload-experiment.jsonl") if l.strip()]
by = collections.OrderedDict()
for r in rows:
    by.setdefault(r["label"], []).append(r)
print("records:", len(rows), "| variants:", {k: len(v) for k, v in by.items()})
for label, rs in by.items():
    print(f"\n== {label} ==")
    print("phase         conc  requests   ok  shed  errors  goodput/s  ok_p50  ok_p95  ok_max  shed_p50")
    for r in rs:
        print(f"{r['phase']:<13} {r['concurrency']:>4} {r['requests']:>9} {r['ok']:>4} {r['shed']:>5} {r['errors']:>7} {r['goodput_per_s']:>10} {str(r['ok_p50_ms']):>7} {str(r['ok_p95_ms']):>7} {str(r['ok_max_ms']):>7} {str(r['shed_p50_ms']):>9}")
summary = {"source": "runs/aws-overload-experiment.jsonl (machine-logged by scripts/aws_loadtest.py, pulled from the router host with RAW=1 scripts/aws_run.sh)",
           "setting": "router host t4g.large (2 vCPU); levels 1,4,8,16,32 in flight, then a recovery check (20 sequential searches right away and 20 s later); one run per variant",
           "variants": {}}
for label, rs in by.items():
    hard = [r for r in rs if r["phase"] == "level"][-1]
    rec0 = next(r for r in rs if r["phase"] == "recovery_0s")
    rec20 = next(r for r in rs if r["phase"].startswith("recovery_") and r["phase"] != "recovery_0s")
    summary["variants"][label] = {"hardest_level": {k: hard[k] for k in ("concurrency", "requests", "ok", "shed", "errors", "goodput_per_s", "ok_p50_ms", "ok_p95_ms", "shed_p50_ms")},
                                  "recovery_0s": {k: rec0[k] for k in ("ok", "errors", "goodput_per_s")}, "recovery_late": {"phase": rec20["phase"], **{k: rec20[k] for k in ("ok", "errors", "goodput_per_s")}},
                                  "goodput_at_4_8_16": [next(r for r in rs if r["phase"] == "level" and r["concurrency"] == c)["goodput_per_s"] for c in (4, 8, 16)]}
json.dump(summary, open("runs/aws-overload-experiment.summary.json", "w"), indent=1)
print("\nwrote runs/aws-overload-experiment.summary.json")
