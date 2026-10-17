"""Check every CloudWatch metric-filter pattern in infra/cloudwatch/metric-filters.json against REAL-shaped log lines, using CloudWatch's own
test API (aws logs test-metric-filter: free, nothing is created). Run it BEFORE deploying the monitoring stack. Uses your AWS login (profile genkart).
Each sample line says which filters must match it; any surprise (a miss, or a match that should not happen) is printed and the exit code is 1.
Usage: .venv/bin/python scripts/test_metric_filters.py"""
import json
import sys

import boto3

filters = {f["id"]: f for f in json.load(open("infra/cloudwatch/metric-filters.json"))}
ROUTER_OK = '{"req":"87d63e43","status":200,"partial":false,"failovers":0,"hedged":4,"encode":250.9,"shards":67.06,"merge":0.53,"total":318.49}'
ROUTER_PARTIAL = '{"req":"a1","status":200,"partial":true,"failovers":1,"hedged":2,"encode":250.1,"shards":812.4,"merge":0.4,"total":1063.2}'
ROUTER_FAILOVER = '{"req":"a2","status":200,"partial":false,"failovers":3,"hedged":1,"encode":249.0,"shards":90.1,"merge":0.3,"total":340.0}'
ROUTER_502 = '{"req":"a3","status":502,"error":"Error: encoder answered 500","total":5003.2}'
ROUTER_429 = '{"req":"b1","status":429,"shed":true,"inflight":12}'
ENCODER_DROP = '{"req":"b2","svc":"encoder","path":"/encode","status":503,"ms":0.4}'
ROUTER_UP = '{"msg":"router up","host":"0.0.0.0","port":9100,"encoder":"http://127.0.0.1:9000","shards":[["http://10.0.0.10:9101","http://10.0.1.10:9101"]],"shardTimeoutMs":800,"hedgeMs":40}'
INGEST_OK = '{"event": "batch", "received": 5, "acked": 5, "failed": 0, "seconds": 2.8, "max_receive_count": 1}'
INGEST_BAD = '{"event": "batch", "received": 3, "acked": 0, "failed": 3, "seconds": 7.84, "max_receive_count": 7}'
INGEST_ERR = '{"event": "step_error", "error": "ClientError: boom"}'
INGEST_TEXT = 'attempt failed (will retry): write: http://10.0.1.10:9103: timed out'
SHARD = '{"req":"87d63e43","svc":"shard","shard":1,"path":"/search","status":200,"ms":6.51}'
SHARD_INGEST = '{"req":"-","svc":"shard","shard":1,"path":"/ingest","status":200,"ms":3.2}'
ENCODER = '{"req":"87d63e43","svc":"encoder","path":"/encode","status":200,"ms":247.3}'
# line -> the filter ids that must match it (and no other)
EXPECT = {
    ROUTER_OK: {"SearchMs", "EncodeMs", "ShardsMs", "Searches"},
    ROUTER_PARTIAL: {"SearchMs", "EncodeMs", "ShardsMs", "Searches", "PartialAnswers", "FailoverRequests"},
    ROUTER_FAILOVER: {"SearchMs", "EncodeMs", "ShardsMs", "Searches", "FailoverRequests"},
    ROUTER_502: {"SearchMs", "Searches", "ServerErrors"},     # a failed search is a search the caller waited for: it counts, with its wait
    ROUTER_429: {"ShedRequests"},
    ENCODER_DROP: {"EncoderRequestMs", "EncoderDropped"},
    ROUTER_UP: set(),
    INGEST_OK: {"IngestAcked"},
    INGEST_BAD: {"IngestAcked", "IngestFailed", "IngestNearDlq"},
    INGEST_ERR: {"IngestStepErrors"},
    INGEST_TEXT: set(),
    SHARD: {"ShardRequestMs"},
    SHARD_INGEST: set(),
    ENCODER: {"EncoderRequestMs"},
}
logs = boto3.Session(profile_name="genkart", region_name="ap-south-1").client("logs")
bad = 0
for line, want in EXPECT.items():
    got = set()
    for f in filters.values():
        r = logs.test_metric_filter(filterPattern=f["pattern"], logEventMessages=[line])
        if r["matches"]:
            got.add(f["id"])
    # filters of another log group never see this line in real life: only judge the ones of the group the line belongs to
    group = "router" if ('"req"' in line and '"svc"' not in line) or '"router up"' in line else "ingest" if ('"event"' in line or "attempt failed" in line) else "shard" if '"svc":"shard"' in line else "encoder"
    got = {g for g in got if filters[g]["group"] == group}
    ok = got == want
    bad += not ok
    print(("OK   " if ok else "WRONG"), line[:70].ljust(70), "matched:", sorted(got) if not ok else len(got), "" if ok else f"wanted: {sorted(want)}")
print("\nALL PATTERNS BEHAVE AS EXPECTED" if not bad else f"\n{bad} line(s) behaved unexpectedly")
sys.exit(1 if bad else 0)
