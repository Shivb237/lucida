"""Send one search per second to the router and print one line each; append every line to a JSONL file (a logged run).
Used for the AWS failover demo: run it, then stop a machine in another window and watch partial/failovers/hedged change.
Standard library only, so it runs on any Mac without the project's virtual environment.
Usage: python3 scripts/aws_probe.py http://ROUTER_IP:9100 [seconds=90] [out=runs/aws-probe.jsonl]"""
import json, sys, time, urllib.request

base = sys.argv[1].rstrip("/")
seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 90
out = sys.argv[3] if len(sys.argv) > 3 else "runs/aws-probe.jsonl"
texts = ["red lehenga for sister sangeet", "men's navy blazer for a winter wedding", "white sneakers for college", "black saree for cocktail party",
         "kids kurta for diwali", "women's yellow kurti set under 1500", "men's formal shoes brown", "summer linen shirt men"]
t0 = time.time(); n = 0; run_id = int(t0)   # run_id keeps runs apart: the output file is appended to, so one file can hold several runs
print("time   status partial shards failovers hedged  total_ms  (what happened)")
while time.time() - t0 < seconds:
    n += 1; t = time.time(); row = {"run": run_id, "t": round(t - t0, 1), "text": texts[n % len(texts)]}
    try:
        req = urllib.request.Request(base + "/search", data=json.dumps({"text": row["text"], "k": 4}).encode(), headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read()); row.update(status=r.status, partial=d["partial"], ok=d["shards"]["ok"], total=d["shards"]["total"], failovers=d["shards"]["failovers"],
                                              hedged=d["shards"]["hedged"], total_ms=d["timings_ms"]["total"], shards_ms=d["timings_ms"]["shards"], top=d["results"][0]["id"] if d["results"] else None)
    except Exception as e:
        row.update(status=0, error=str(e)[:80], total_ms=round((time.time() - t) * 1000, 1))
    with open(out, "a") as f:
        f.write(json.dumps(row) + "\n")
    note = row.get("error", "") or ("PARTIAL ANSWER" if row.get("partial") else ("failover used" if row.get("failovers") else ""))
    print(f"{row['t']:5.1f}  {row['status']:>6} {str(row.get('partial','-')):>7} {row.get('ok','-')}/{row.get('total','-')}    {str(row.get('failovers','-')):>5}  {str(row.get('hedged','-')):>5} {row['total_ms']:>9}  {note}", flush=True)
    time.sleep(max(0, 1 - (time.time() - t)))
