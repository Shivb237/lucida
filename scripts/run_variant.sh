#!/bin/bash
# Switch the router host to one overload-handling variant and load-test it, in one command (runs on the Mac, works on the router through SSM).
# Usage: source scripts/aws_env.sh; ROUTER_ID=<id> scripts/run_variant.sh baseline|v1|v2      (about 4-6 minutes; results append to /tmp/experiment.jsonl ON the router)
set -euo pipefail
V="${1:?usage: run_variant.sh baseline|v1|v2}"
: "${B:?run: source scripts/aws_env.sh first}"
ID="${ROUTER_ID:?set ROUTER_ID to the router host instance id (cdk output RouterHostId, or: aws ec2 describe-instances); machines are replaced, so an old id would silently hit a machine that no longer exists}"
cd "$(dirname "$0")/.."
echo "== switching to variant $V =="
scripts/aws_run.sh "$ID" "bash -c 'aws s3 cp s3://$B/shards/code/set-variant.sh /tmp/sv.sh --only-show-errors && AWS_DEFAULT_REGION=ap-south-1 bash /tmp/sv.sh $V'"
echo "== load test, label $V (levels 1,4,8,16,32, then the recovery check) =="
scripts/aws_run.sh "$ID" "bash -c 'aws s3 cp s3://$B/shards/code/aws_loadtest.py /tmp/lt.py --only-show-errors && AWS_DEFAULT_REGION=ap-south-1 python3 /tmp/lt.py http://127.0.0.1:9100 1,4,8,16,32 40 /tmp/experiment.jsonl $V'"
