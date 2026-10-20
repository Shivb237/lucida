#!/bin/bash
# Run ON the router host, as root (SSM Run Command does that). Applies the observability update by hand, the same steps a rebuilt machine
# would do from its startup script: new program files, new service recipes (logs to files), log rotation, CloudWatch agent config.
# Safe to run again. Prints UPDATE OK only when every service is active, the router answers /health and one real POST /search returns results.
# The Python requirements (CPU torch lock, encoder lock, ingest lock) are reinstalled, hash-checked, only when one of them changed since the last run.
# Usage: apply-router-update.sh <bucket-name> [<shard-token-secret-arn>]   (the ARN is the GenkartCompute output ShardTokenSecretArn; given, the
# token is (re)written into router.env as SHARD_TOKEN and ingest.env as GENKART_SHARD_TOKEN; it is never printed)
set -euo pipefail
export AWS_DEFAULT_REGION=ap-south-1
B="${1:-}"; [ -n "$B" ] || { echo "usage: $0 <bucket-name> [<shard-token-secret-arn>] (the bucket name was empty)"; exit 2; }        # the bucket name
SECRET="${2:-}"
cd /opt/genkart
# the router ships compiled for Node 22+ (dist/, plain JavaScript): an older Node would fail at start, after the old router was stopped
command -v node >/dev/null 2>&1 && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] \
  || { echo "NODE TOO OLD OR MISSING: $(node --version 2>/dev/null || echo none); install nodejs24 (dnf install -y nodejs24). Nothing was changed."; exit 1; }
for f in genkart-encoder-src.tgz genkart-router-src.tgz genkart-ingest-src.tgz requirements-torch-cpu.txt requirements-encoder.txt requirements-ingest.txt genkart-encoder.service genkart-router.service genkart-ingest.service genkart-logrotate.conf genkart-tmpfiles.conf router-agent.json; do
  aws s3 cp "s3://$B/shards/code/$f" . --only-show-errors
done
tar --no-same-owner -xzf genkart-encoder-src.tgz 2>/dev/null; tar --no-same-owner -xzf genkart-ingest-src.tgz 2>/dev/null; tar --no-same-owner -xzf genkart-router-src.tgz -C router 2>/dev/null
[ -f router/dist/index.js ] || { echo 'ROUTER PACKAGE HAS NO dist/index.js: rebuild it with scripts/package_shard_code.sh'; exit 1; }   # the unit now runs the compiled router
if [ -n "$SECRET" ]; then
  TOKEN="$(aws secretsmanager get-secret-value --secret-id "$SECRET" --query SecretString --output text)"
  [ -n "$TOKEN" ] || { echo 'EMPTY SHARD TOKEN'; exit 1; }
  sed -i '/^SHARD_TOKEN=/d' /etc/genkart/router.env; sed -i '/^GENKART_SHARD_TOKEN=/d' /etc/genkart/ingest.env
  printf 'SHARD_TOKEN=%s\n' "$TOKEN" >> /etc/genkart/router.env
  printf 'GENKART_SHARD_TOKEN=%s\n' "$TOKEN" >> /etc/genkart/ingest.env
  unset TOKEN
  chown root:genkart /etc/genkart/router.env /etc/genkart/ingest.env; chmod 0640 /etc/genkart/router.env /etc/genkart/ingest.env
  echo "shard token written (router.env, ingest.env)"
fi
# requirements: same order and flags as the startup script (CPU torch first, --no-deps, then the locks; all hash-checked). The sha256 of the three
# locks as installed is kept in the venv, so an unchanged lock costs nothing; a host from before this script has no record and installs once
REQ_SUM="$(sha256sum requirements-torch-cpu.txt requirements-encoder.txt requirements-ingest.txt)"
if [ "$REQ_SUM" != "$(cat .venv/.genkart-requirements.sha256 2>/dev/null)" ]; then
  echo "requirements changed: reinstalling"
  export TMPDIR=/var/tmp   # pip's temporary files on the disk, not in the small memory-backed /tmp
  .venv/bin/pip install -q --no-cache-dir --require-hashes --no-deps --index-url https://download.pytorch.org/whl/cpu -r requirements-torch-cpu.txt
  .venv/bin/pip install -q --no-cache-dir -r requirements-encoder.txt
  .venv/bin/pip install -q --no-cache-dir -r requirements-ingest.txt
  printf '%s\n' "$REQ_SUM" > .venv/.genkart-requirements.sha256
else
  echo "requirements unchanged"
fi
cp genkart-encoder.service genkart-router.service genkart-ingest.service /etc/systemd/system/
cp genkart-logrotate.conf /etc/logrotate.d/genkart
cp genkart-tmpfiles.conf /etc/tmpfiles.d/genkart.conf
systemd-tmpfiles --create /etc/tmpfiles.d/genkart.conf
[ -d /var/log/genkart ] || { echo 'LOG FOLDER MISSING: /var/log/genkart'; exit 1; }   # systemd cannot open a log file in a missing folder (status 209/STDOUT)
# code and venv belong to root (the units mount them read-only); genkart owns only the folders in the units' ReadWritePaths, which must exist
chown -R root:root /opt/genkart
mkdir -p /opt/genkart/.cache /opt/genkart/data/ingest-photos
chown -R genkart:genkart /opt/genkart/.cache /opt/genkart/data
systemctl daemon-reload
systemctl restart genkart-encoder genkart-router genkart-ingest
command -v amazon-cloudwatch-agent-ctl >/dev/null 2>&1 || [ -x /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl ] || dnf install -y -q amazon-cloudwatch-agent > /dev/null
cp router-agent.json /opt/aws/amazon-cloudwatch-agent/etc/router-agent.json
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/router-agent.json -s > /dev/null
for i in $(seq 1 40); do                  # the encoder needs about a minute to load its model
  if curl -sf --max-time 3 http://127.0.0.1:9100/health | grep -q '"encoder":true'; then break; fi; sleep 5
done
for u in genkart-encoder:encoder genkart-router:router genkart-ingest:ingest amazon-cloudwatch-agent:-; do
  unit="${u%%:*}"; log="${u#*:}"
  if ! systemctl is-active --quiet "$unit"; then
    echo "NOT ACTIVE: $unit ($(systemctl is-active "$unit"))"; journalctl -u "$unit" -n 6 --no-pager | cut -c1-200
    [ "$log" != "-" ] && tail -15 "/var/log/genkart/$log.log" 2>/dev/null
    exit 1
  fi
  echo "active: $unit"
done
curl -sf --max-time 3 http://127.0.0.1:9100/health || { echo 'router does not answer /health'; tail -15 /var/log/genkart/router.log /var/log/genkart/encoder.log; exit 1; }; echo
# one real search end to end (encoder, every shard, merge): /health only says the parts are up, not that they answer a search together
ANSWER="$(curl -sf --max-time 10 -X POST http://127.0.0.1:9100/search -H 'content-type: application/json' -H 'x-request-id: apply-update' -d '{"text":"red dress","k":2}')" \
  || { echo 'POST /search FAILED'; tail -15 /var/log/genkart/router.log; exit 1; }
grep -q '"results":\[{' <<< "$ANSWER" || { echo "POST /search RETURNED NO RESULTS: $ANSWER"; exit 1; }
SHARDS="$(grep -o '"shards":{[^}]*}' <<< "$ANSWER" || true)"
if grep -q '"partial":false' <<< "$ANSWER"; then echo "search ok: $SHARDS"; else echo "search ok but PARTIAL (a shard did not answer): $SHARDS"; fi
ls -l /var/log/genkart/
echo "UPDATE OK"
