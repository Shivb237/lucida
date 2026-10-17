"""Run a CloudWatch Logs Insights query from the Mac and print the result as a table (no console clicking).
Usage: .venv/bin/python scripts/logs_query.py GROUP[,GROUP...] "<query>" [hours=3]
Example: .venv/bin/python scripts/logs_query.py /genkart/encoder 'filter svc = "encoder" | stats count() as n, max(ms) as slowest by bin(1m) | sort @timestamp' 3
Uses your AWS login (profile genkart). Insights queries are billed per GB scanned (our logs are tiny)."""
import sys
import time

import boto3

groups = sys.argv[1].split(",")
query = sys.argv[2]
hours = float(sys.argv[3]) if len(sys.argv) > 3 else 3
logs = boto3.Session(profile_name="genkart", region_name="ap-south-1").client("logs")
now = int(time.time())
qid = logs.start_query(logGroupNames=groups, startTime=now - int(hours * 3600), endTime=now, queryString=query, limit=200)["queryId"]
while True:
    r = logs.get_query_results(queryId=qid)
    if r["status"] in ("Complete", "Failed", "Cancelled", "Timeout"):
        break
    time.sleep(1)
if r["status"] != "Complete":
    sys.exit(f"query {r['status']}")
def shown(field, value):
    # @log looks like "<account number>:/genkart/router": drop the account number so a screenshot never carries it
    return value.split(":", 1)[1] if field == "@log" and ":" in value else value


rows = [{c["field"]: shown(c["field"], c["value"]) for c in row if c["field"] != "@ptr"} for row in r["results"]]
if not rows:
    print("(no rows: no matching log lines in that time range)")
else:
    cols = list(rows[0].keys())
    print("  ".join(c[:24].ljust(24) for c in cols))
    for row in rows:
        print("  ".join(str(row.get(c, ""))[:24].ljust(24) for c in cols))
print(f"\n{len(rows)} row(s); scanned {r['statistics'].get('bytesScanned', 0):.0f} bytes")
