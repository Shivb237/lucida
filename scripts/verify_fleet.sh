#!/bin/bash
# Ask the three machines (through SSM) whether the startup script finished and everything is running. Usage: source scripts/aws_env.sh; scripts/verify_fleet.sh <routerId> <shardAId> <shardBId>
set -uo pipefail
R="${1:?router id}"; A="${2:?shard A id}"; BB="${3:?shard B id}"
cd "$(dirname "$0")/.."
echo "=== ROUTER $R ==="
RAW=1 scripts/aws_run.sh "$R" 'test -f /opt/genkart/.bootstrapped && echo "bootstrapped: yes" || echo "bootstrapped: NO"; test -f /opt/genkart/.bootstrap-failed && echo "bootstrap-failed marker PRESENT"; for u in genkart-encoder genkart-router genkart-ingest amazon-cloudwatch-agent; do echo "$u: $(systemctl is-active $u)"; done; echo "variant (defaults when the env files hold no override): $(cat /etc/genkart/encoder.env 2>/dev/null || echo "no encoder.env -> ENCODER_CONCURRENCY default 2") | $(grep MAX_INFLIGHT /etc/genkart/router.env || echo "no MAX_INFLIGHT -> default 12")"; echo "instance type: $(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")" http://169.254.169.254/latest/meta-data/instance-type)"; ls -l /var/log/genkart/ | tail -n +2'
for H in "$A" "$BB"; do
  echo "=== SHARD HOST $H ==="
  RAW=1 scripts/aws_run.sh "$H" 'test -f /opt/genkart/.bootstrapped && echo "bootstrapped: yes" || echo "bootstrapped: NO"; test -f /opt/genkart/.bootstrap-failed && echo "bootstrap-failed marker PRESENT"; for i in 0 1 2 3; do echo "genkart-shard@$i: $(systemctl is-active genkart-shard@$i)"; done; echo "amazon-cloudwatch-agent: $(systemctl is-active amazon-cloudwatch-agent)"; for p in 9101 9102 9103 9104; do curl -s --max-time 3 localhost:$p/health; echo; done; ls -l /var/log/genkart/ | tail -n +2'
done
