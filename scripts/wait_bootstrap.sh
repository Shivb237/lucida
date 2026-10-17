#!/bin/bash
# Wait until a freshly built machine has finished its startup script. Runs on the Mac, asks the machine through SSM every 30 s (up to 30 minutes).
# Prints BOOTSTRAPPED (success), or FAILED plus the end of /var/log/genkart-bootstrap.log. Usage: scripts/wait_bootstrap.sh <instance-id>
set -uo pipefail
ID="${1:?usage: wait_bootstrap.sh <instance-id>}"
cd "$(dirname "$0")/.."
for i in $(seq 1 60); do
  out=$(scripts/aws_run.sh "$ID" 'if [ -f /opt/genkart/.bootstrapped ]; then echo BOOTSTRAPPED; elif [ -f /opt/genkart/.bootstrap-failed ]; then echo FAILED; tail -30 /var/log/genkart-bootstrap.log; else echo "WAITING: $(tail -1 /var/log/genkart-bootstrap.log 2>/dev/null | cut -c1-90)"; fi' 2>&1 || true)
  echo "[$(date +%H:%M:%S) try $i] $(echo "$out" | head -40)"
  case "$out" in *BOOTSTRAPPED*) exit 0 ;; *FAILED*) exit 1 ;; esac
  sleep 30
done
echo "gave up after 30 minutes"; exit 2
