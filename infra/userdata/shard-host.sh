#!/bin/bash
# Runs ONCE, as root, the first time a shard host boots (EC2 "user data"). Same steps you ran by hand on shard host A.
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
id genkart >/dev/null 2>&1 || useradd --system --home-dir /opt/genkart --shell /sbin/nologin genkart
mkdir -p /opt/genkart /etc/genkart && cd /opt/genkart

# the shard token (callers must send it as x-genkart-token; /ingest is refused without it), from Secrets Manager into a file only root and
# genkart can read. Tracing is off for these lines (set +x) so the secret never reaches the bootstrap log.
set +x
TOKEN="$(aws secretsmanager get-secret-value --secret-id "$SHARD_TOKEN_SECRET" --query SecretString --output text)"
[ -n "$TOKEN" ] || { echo "BOOTSTRAP FAILED: empty shard token"; touch /opt/genkart/.bootstrap-failed; exit 1; }
install -m 0640 -o root -g genkart /dev/null /etc/genkart/shard.env
printf 'GENKART_SHARD_TOKEN=%s\n' "$TOKEN" > /etc/genkart/shard.env
unset TOKEN
set -x

aws s3 sync "s3://$BUCKET/shards/n4/" shards/n4/
for f in genkart-shard-src.tgz requirements-shard.txt "genkart-shard@.service" genkart-logrotate.conf genkart-tmpfiles.conf shard-agent.json; do aws s3 cp "s3://$BUCKET/shards/code/$f" .; done
tar --no-same-owner -xzf genkart-shard-src.tgz   # the files belong to root here, not to the Mac user id stored in the archive

python3.12 -m venv .venv
.venv/bin/pip install -r requirements-shard.txt

cp "genkart-shard@.service" /etc/systemd/system/
cp genkart-logrotate.conf /etc/logrotate.d/genkart
cp genkart-tmpfiles.conf /etc/tmpfiles.d/genkart.conf
systemd-tmpfiles --create /etc/tmpfiles.d/genkart.conf
[ -d /var/log/genkart ]       # the services write their logs there: systemd fails with status 209/STDOUT if the folder is missing
# code and venv stay root's (the workers see them read-only: ProtectSystem=strict in the unit); genkart owns only the shard folder, where each
# worker appends its write-ahead log (the unit's ReadWritePaths)
chown -R root:root /opt/genkart
chown -R genkart:genkart /opt/genkart/shards
systemctl daemon-reload
systemctl enable --now genkart-shard@0 genkart-shard@1 genkart-shard@2 genkart-shard@3
sleep 15
for i in 0 1 2 3; do   # every worker must be up and answering, not just "some unit is active"
  systemctl is-active --quiet "genkart-shard@$i" && curl -sf --max-time 5 "localhost:$((9101 + i))/health" > /dev/null \
    || { echo "BOOTSTRAP FAILED: shard worker $i"; journalctl -u "genkart-shard@$i" -n 20 --no-pager; touch /opt/genkart/.bootstrap-failed; exit 1; }
done

# logs and metrics to CloudWatch (the agent reads /var/log/genkart/*.log)
dnf install -y -q amazon-cloudwatch-agent > /dev/null
cp shard-agent.json /opt/aws/amazon-cloudwatch-agent/etc/shard-agent.json
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/shard-agent.json -s > /dev/null
systemctl is-active --quiet amazon-cloudwatch-agent || { echo "BOOTSTRAP FAILED: cloudwatch agent"; touch /opt/genkart/.bootstrap-failed; exit 1; }
touch /opt/genkart/.bootstrapped
