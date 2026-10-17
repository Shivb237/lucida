#!/bin/bash
# Runs ONCE, as root, the first time the router host boots. Installs the encoder (Python + torch) and the TypeScript router.
# Progress and errors: /var/log/genkart-bootstrap.log   (also /var/log/cloud-init-output.log)
exec > >(tee /var/log/genkart-bootstrap.log) 2>&1
set -euxo pipefail
BUCKET="{{BUCKET}}"
export AWS_DEFAULT_REGION=ap-south-1

dnf install -y python3.12
# Node must be able to run .ts files: 22.18+ or 24. Try the newest package Amazon offers.
dnf install -y nodejs24 || dnf install -y nodejs22 || dnf install -y nodejs
node --version
id genkart >/dev/null 2>&1 || useradd --system --home-dir /opt/genkart --shell /sbin/nologin genkart
mkdir -p /opt/genkart/router /etc/genkart && cd /opt/genkart

for f in genkart-encoder-src.tgz genkart-router-src.tgz genkart-ingest-src.tgz requirements-encoder.txt requirements-ingest.txt \
         genkart-encoder.service genkart-router.service genkart-ingest.service genkart-logrotate.conf genkart-tmpfiles.conf router-agent.json; do
  aws s3 cp "s3://$BUCKET/shards/code/$f" .
done
tar -xzf genkart-encoder-src.tgz
tar -xzf genkart-ingest-src.tgz
tar -xzf genkart-router-src.tgz -C router

python3.12 -m venv .venv
# pip's temporary files go on the disk (the default /tmp is small, memory-backed space)
export TMPDIR=/var/tmp
# CPU-only torch from PyTorch's own address. A plain `pip install torch` on this ARM machine pulls the GPU build
# (several GB of nvidia packages) and ran the machine out of space on the first try (2026-10-15). The extra index
# only supplies torch's small dependencies; 2.14.1+cpu ranks above plain 2.14.1, so the CPU build is the one chosen.
.venv/bin/pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple torch==2.14.1 torchvision==0.29.1
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

cp genkart-encoder.service genkart-router.service genkart-ingest.service /etc/systemd/system/
cp genkart-logrotate.conf /etc/logrotate.d/genkart
cp genkart-tmpfiles.conf /etc/tmpfiles.d/genkart.conf
systemd-tmpfiles --create /etc/tmpfiles.d/genkart.conf
[ -d /var/log/genkart ]       # the services write their logs there: systemd fails with status 209/STDOUT if the folder is missing
chown -R genkart:genkart /opt/genkart
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
