#!/bin/bash
# Run a shell command ON an EC2 machine from your Mac, through SSM Run Command (no black screen, no open port), wait, print what it printed.
# The command runs as root on the machine. Usage:  scripts/aws_run.sh <instance-id> '<command>'
# Needs your AWS login (AWS_PROFILE=genkart). Prints: Status, then the command's output, then its error output.
# RAW=1 prints ONLY the command's output (so it can be redirected into a file).
set -euo pipefail
ID="$1"; CMD="$2"
PARAMS=$(python3 -c 'import json,sys; print(json.dumps({"commands": [sys.argv[1]]}))' "$CMD")
CID=$(aws ssm send-command --region ap-south-1 --instance-ids "$ID" --document-name AWS-RunShellScript --parameters "$PARAMS" --query Command.CommandId --output text)
errors=0
for _ in $(seq 1 720); do                      # at most about an hour; a command left running longer is not "waiting" any more
  if S=$(aws ssm get-command-invocation --region ap-south-1 --command-id "$CID" --instance-id "$ID" --query Status --output text 2>/dev/null); then errors=0; else S=Pending; errors=$((errors+1)); fi
  # an expired login or a deleted machine makes every call fail: say so after about a minute instead of waiting for ever
  [ "$errors" -ge 12 ] && { echo "aws ssm get-command-invocation keeps failing (login expired? machine gone?): run 'aws sso login --profile genkart' and try again" >&2; exit 3; }
  case "$S" in Pending|InProgress|Delayed) sleep 5 ;; *) break ;; esac
done
if [ -n "${RAW:-}" ]; then
  aws ssm get-command-invocation --region ap-south-1 --command-id "$CID" --instance-id "$ID" --query StandardOutputContent --output text
else
  aws ssm get-command-invocation --region ap-south-1 --command-id "$CID" --instance-id "$ID" --query '[Status,StandardOutputContent,StandardErrorContent]' --output text
fi
