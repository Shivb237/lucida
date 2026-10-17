#!/bin/bash
# Run ON the router host, as root (SSM Run Command does that). Applies the observability update by hand, the same steps a rebuilt machine
# would do from its startup script: new program files, new service recipes (logs to files), log rotation, CloudWatch agent config.
# Safe to run again. Prints UPDATE OK only when every service is active and the router answers /health.
set -euo pipefail
export AWS_DEFAULT_REGION=ap-south-1
B="${1:-}"; [ -n "$B" ] || { echo "usage: $0 <bucket-name> (the bucket name was empty)"; exit 2; }                                    # the bucket name
cd /opt/genkart
for f in genkart-encoder-src.tgz genkart-router-src.tgz genkart-ingest-src.tgz genkart-encoder.service genkart-router.service genkart-ingest.service genkart-logrotate.conf genkart-tmpfiles.conf router-agent.json; do
  aws s3 cp "s3://$B/shards/code/$f" . --only-show-errors
done
tar -xzf genkart-encoder-src.tgz 2>/dev/null; tar -xzf genkart-ingest-src.tgz 2>/dev/null; tar -xzf genkart-router-src.tgz -C router 2>/dev/null
cp genkart-encoder.service genkart-router.service genkart-ingest.service /etc/systemd/system/
cp genkart-logrotate.conf /etc/logrotate.d/genkart
cp genkart-tmpfiles.conf /etc/tmpfiles.d/genkart.conf
systemd-tmpfiles --create /etc/tmpfiles.d/genkart.conf
[ -d /var/log/genkart ] || { echo 'LOG FOLDER MISSING: /var/log/genkart'; exit 1; }   # systemd cannot open a log file in a missing folder (status 209/STDOUT)
chown -R genkart:genkart /opt/genkart
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
ls -l /var/log/genkart/
echo "UPDATE OK"
