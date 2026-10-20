#!/bin/bash
# Runs ONCE, as root, the first time the router host boots. Installs the encoder (Python + torch), the router (compiled TypeScript) and the ingest worker.
# Progress and errors: /var/log/genkart-bootstrap.log   (also /var/log/cloud-init-output.log)
exec > >(tee /var/log/genkart-bootstrap.log) 2>&1
set -euxo pipefail
BUCKET="{{BUCKET}}"
SHARD_TOKEN_SECRET="{{SHARD_TOKEN_SECRET}}"   # the secret's address (ARN), not the secret
export AWS_DEFAULT_REGION=ap-south-1
# any failing command (set -e) leaves the failure marker too, not only the checks that write it themselves; the folder must exist first.
# -E: the trap also fires inside functions and subshells
mkdir -p /opt/genkart
set -E
trap 'touch /opt/genkart/.bootstrap-failed' ERR

dnf install -y python3.12
# The router ships compiled (dist/index.js, plain JavaScript): Node 22 or newer. Amazon Linux's plain "nodejs" package is older, so it is not a fallback.
dnf install -y nodejs24 || dnf install -y nodejs22
node --version
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] || { echo "BOOTSTRAP FAILED: node $(node --version) is older than 22"; touch /opt/genkart/.bootstrap-failed; exit 1; }
id genkart >/dev/null 2>&1 || useradd --system --home-dir /opt/genkart --shell /sbin/nologin genkart
mkdir -p /opt/genkart/router /etc/genkart && cd /opt/genkart

for f in genkart-encoder-src.tgz genkart-router-src.tgz genkart-ingest-src.tgz requirements-torch-cpu.txt requirements-encoder.txt requirements-ingest.txt \
         genkart-encoder.service genkart-router.service genkart-ingest.service genkart-logrotate.conf genkart-tmpfiles.conf router-agent.json; do
  aws s3 cp "s3://$BUCKET/shards/code/$f" .
done
# --no-same-owner: the files belong to root here, not to the Mac user id stored in the archive
tar --no-same-owner -xzf genkart-encoder-src.tgz
tar --no-same-owner -xzf genkart-ingest-src.tgz
tar --no-same-owner -xzf genkart-router-src.tgz -C router

python3.12 -m venv .venv
# pip's temporary files go on the disk (the default /tmp is small, memory-backed space)
export TMPDIR=/var/tmp
# CPU-only torch from PyTorch's own address. A plain `pip install torch` on this ARM machine pulls the GPU build
# (several GB of nvidia packages) and ran the machine out of space on the first try (2026-10-15). Hash-checked like everything else:
# requirements-torch-cpu.txt (space/, made by scripts/lock.sh, uploaded with the code packages) pins 2.14.1+cpu with the sha256 PyTorch's
# index publishes, cp312 manylinux aarch64 included. --no-deps: torch's own dependencies (sympy, networkx, jinja2, ...) are in the
# encoder lock, installed next with their hashes; that lock leaves torch out and finds 2.14.1+cpu already there.
.venv/bin/pip install --no-cache-dir --require-hashes --no-deps --index-url https://download.pytorch.org/whl/cpu -r requirements-torch-cpu.txt
.venv/bin/pip install --no-cache-dir -r requirements-encoder.txt
.venv/bin/pip install --no-cache-dir -r requirements-ingest.txt     # the ingest worker (SQS + S3 + HTTP): without this line a rebuilt router would lose it

cat > /etc/genkart/router.env <<ENVEOF
HOST=0.0.0.0
PORT=9100
ENCODER_URL=http://127.0.0.1:9000
SHARD_URLS="{{SHARD_URLS}}"
ENVEOF

cat > /etc/genkart/ingest.env <<ENVEOF
SQS_QUEUE_URL={{QUEUE_URL}}
SQS_DLQ_URL={{DLQ_URL}}
ENVEOF

# the shard token (the shards refuse /ingest without it): the router sends it as SHARD_TOKEN, the ingest worker as GENKART_SHARD_TOKEN.
# Both env files become root:genkart 0640. Tracing is off for these lines (set +x) so the secret never reaches the bootstrap log.
chown root:genkart /etc/genkart/router.env /etc/genkart/ingest.env
chmod 0640 /etc/genkart/router.env /etc/genkart/ingest.env
set +x
TOKEN="$(aws secretsmanager get-secret-value --secret-id "$SHARD_TOKEN_SECRET" --query SecretString --output text)"
[ -n "$TOKEN" ] || { echo "BOOTSTRAP FAILED: empty shard token"; touch /opt/genkart/.bootstrap-failed; exit 1; }
printf 'SHARD_TOKEN=%s\n' "$TOKEN" >> /etc/genkart/router.env
printf 'GENKART_SHARD_TOKEN=%s\n' "$TOKEN" >> /etc/genkart/ingest.env
unset TOKEN
set -x

cp genkart-encoder.service genkart-router.service genkart-ingest.service /etc/systemd/system/
cp genkart-logrotate.conf /etc/logrotate.d/genkart
cp genkart-tmpfiles.conf /etc/tmpfiles.d/genkart.conf
systemd-tmpfiles --create /etc/tmpfiles.d/genkart.conf
[ -d /var/log/genkart ]       # the services write their logs there: systemd fails with status 209/STDOUT if the folder is missing
# code and venv stay root's (the services see them read-only: ProtectSystem=strict in the units); genkart owns only what the services write,
# the folders named in each unit's ReadWritePaths (they must exist, or the unit does not start)
chown -R root:root /opt/genkart
mkdir -p /opt/genkart/.cache /opt/genkart/data/ingest-photos
chown -R genkart:genkart /opt/genkart/.cache /opt/genkart/data
systemctl daemon-reload
systemctl enable --now genkart-encoder genkart-router genkart-ingest

# the encoder downloads its model on the first start (a few minutes): wait until the router reports it, up to 10 minutes
for i in $(seq 1 120); do
  curl -sf --max-time 3 http://127.0.0.1:9100/health | grep -q '"encoder":true' && break
  sleep 5
done
for u in genkart-encoder genkart-router genkart-ingest; do   # every service must be up: `systemctl is-active a b c` passes if only ONE is
  systemctl is-active --quiet "$u" || { echo "BOOTSTRAP FAILED: $u"; journalctl -u "$u" -n 20 --no-pager; tail -20 "/var/log/genkart/${u#genkart-}.log" || true; touch /opt/genkart/.bootstrap-failed; exit 1; }
done
curl -sf --max-time 3 http://127.0.0.1:9100/health | grep -q '"encoder":true' || { echo "BOOTSTRAP FAILED: router does not report the encoder"; touch /opt/genkart/.bootstrap-failed; exit 1; }

# logs and metrics to CloudWatch (the agent reads /var/log/genkart/*.log)
dnf install -y -q amazon-cloudwatch-agent > /dev/null
cp router-agent.json /opt/aws/amazon-cloudwatch-agent/etc/router-agent.json
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/router-agent.json -s > /dev/null
systemctl is-active --quiet amazon-cloudwatch-agent || { echo "BOOTSTRAP FAILED: cloudwatch agent"; touch /opt/genkart/.bootstrap-failed; exit 1; }
touch /opt/genkart/.bootstrapped
