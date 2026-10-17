"""Load test for the router. Standard library only, Python 3.9+ (the router host's default python3), so it runs on the AWS machine with no installs.
For each concurrency level (1, 2, 4, ...) it sends N searches with that many in flight at once and reports, separately:
  ok      answered 200            shed   answered 429 "busy" (the router refused at once: that is the point of the limit, not a failure)
  errors  anything else (502, timeouts, connection problems)
and goodput = ok searches per second (what users actually get). After the last level it runs a RECOVERY check: 20 searches one at a time, right away
and again 20 s later. If the machine is still struggling although the load has stopped, the damage outlasts the load.
Run it ON the router host (SSM) so your home network is not part of the measurement:
  python3 aws_loadtest.py http://127.0.0.1:9100 [levels=1,4,8,16,32] [per_level_minimum=40] [out=/tmp/loadtest.jsonl] [label=unlabelled]
Each level sends max(per_level_minimum, 10 x concurrency) requests then stops: the test is finite on purpose. Every query text differs, so nothing can come from a cache."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

WORDS = ["red", "blue", "black", "white", "green", "yellow", "pink", "navy"]
THINGS = ["kurta", "saree", "lehenga", "jeans", "shirt", "dress", "sneakers", "jacket", "sherwani", "co-ord set"]
WHO = ["women's", "men's", "kids'", "festive", "office", "wedding guest", "summer", "winter"]


def text_for(i):
    return f"{WHO[i % len(WHO)]} {WORDS[(i // 3) % len(WORDS)]} {THINGS[(i // 7) % len(THINGS)]} {i}"


def one(base, i):
    t = time.perf_counter()
    kind, err = "error", None
    try:
        req = urllib.request.Request(base + "/search", data=json.dumps({"text": text_for(i), "k": 4}).encode(), headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            json.loads(r.read())
        kind = "ok"
    except urllib.error.HTTPError as e:
        kind, err = ("shed", None) if e.code == 429 else ("error", f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        err = str(e)[:60]
    return {"ms": (time.perf_counter() - t) * 1000, "kind": kind, "error": err}


def cpu_times():
    try:
        v = [int(x) for x in open("/proc/stat").readline().split()[1:]]
        return sum(v), v[3] + v[4]               # total, idle+iowait
    except OSError:
        return None


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))], 1)


def run_level(base, c, n, counter, lock, label, phase):
    def nxt():
        with lock:
            counter[0] += 1
            return counter[0]

    c0, t0 = cpu_times(), time.perf_counter()
    with ThreadPoolExecutor(max_workers=c) as pool:
        rows = list(pool.map(lambda _: one(base, nxt()), range(n)))
    wall, c1 = time.perf_counter() - t0, cpu_times()
    busy = round(100 * (1 - (c1[1] - c0[1]) / max(1, c1[0] - c0[0])), 1) if c0 and c1 else None
    ok = [r["ms"] for r in rows if r["kind"] == "ok"]
    shed = [r["ms"] for r in rows if r["kind"] == "shed"]
    return {"label": label, "phase": phase, "concurrency": c, "requests": n, "seconds": round(wall, 2), "ok": len(ok), "shed": len(shed), "errors": n - len(ok) - len(shed),
            "goodput_per_s": round(len(ok) / wall, 2), "ok_p50_ms": pct(ok, .5), "ok_p95_ms": pct(ok, .95), "ok_p99_ms": pct(ok, .99), "ok_max_ms": pct(ok, 1.0),
            "shed_p50_ms": pct(shed, .5), "cpu_busy_pct": busy, "first_error": next((r["error"] for r in rows if r["kind"] == "error"), None)}


def show(rec):
    print(f"{rec['phase']:<12} {rec['concurrency']:>4} {rec['requests']:>7} {rec['ok']:>5} {rec['shed']:>5} {rec['errors']:>6}  {rec['goodput_per_s']:>7}  {str(rec['ok_p50_ms']):>8} {str(rec['ok_p95_ms']):>8} {str(rec['shed_p50_ms']):>8}  {rec['cpu_busy_pct']}", flush=True)


def run(base, levels, minimum, out, label="unlabelled", recovery_wait=20, gap=3):
    counter, lock = [0], threading.Lock()
    print(f"label: {label}")
    print("phase        conc requests    ok  shed errors  goodput/s  ok_p50  ok_p95  shed_p50  cpu%")
    stopped = False
    for c in levels:
        rec = run_level(base, c, max(minimum, 10 * c), counter, lock, label, "level")
        with open(out, "a") as f:
            f.write(json.dumps(rec) + "\n")
        show(rec)
        if rec["errors"] > rec["requests"] * 0.2:
            print("stopping the levels: more than 20% of requests FAILED (not counting refused-busy) at this level")
            stopped = True
            break
        time.sleep(gap)
    for wait, phase in ((0, "recovery_0s"), (recovery_wait, "recovery_" + str(recovery_wait) + "s")):
        time.sleep(wait)
        rec = run_level(base, 1, 20, counter, lock, label, phase)
        with open(out, "a") as f:
            f.write(json.dumps(rec) + "\n")
        show(rec)
    return stopped


if __name__ == "__main__":
    a = sys.argv
    run(a[1].rstrip("/"), [int(x) for x in (a[2] if len(a) > 2 else "1,4,8,16,32").split(",")], int(a[3]) if len(a) > 3 else 40,
        a[4] if len(a) > 4 else "/tmp/loadtest.jsonl", a[5] if len(a) > 5 else "unlabelled")
