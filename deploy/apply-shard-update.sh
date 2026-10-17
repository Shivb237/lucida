#!/bin/bash
# Run ON a shard host, as root. Same idea as apply-router-update.sh for the shard workers. Safe to run again.
set -euo pipefail
export AWS_DEFAULT_REGION=ap-south-1
B="${1:-}"; [ -n "$B" ] || { echo "usage: $0 <bucket-name> (the bucket name was empty)"; exit 2; }
cd /opt/genkart
for f in genkart-shard-src.tgz "genkart-shard@.service" genkart-logrotate.conf genkart-tmpfiles.conf shard-agent.json; do
  aws s3 cp "s3://$B/shards/code/$f" . --only-show-errors
done
tar -xzf genkart-shard-src.tgz 2>/dev/null
cp "genkart-shard@.service" /etc/systemd/system/
cp genkart-logrotate.conf /etc/logrotate.d/genkart
cp genkart-tmpfiles.conf /etc/tmpfiles.d/genkart.conf
systemd-tmpfiles --create /etc/tmpfiles.d/genkart.conf
[ -d /var/log/genkart ] || { echo 'LOG FOLDER MISSING: /var/log/genkart'; exit 1; }   # systemd cannot open a log file in a missing folder (status 209/STDOUT)
chown -R genkart:genkart /opt/genkart
# the new code refuses shard files that need pickle (it can run code): check them BEFORE restarting, so a bad file stops the update instead of taking all four workers down
for f in /opt/genkart/shards/n4/shard-*.npz; do
  PYTHONPATH=/opt/genkart/src /opt/genkart/.venv/bin/python -c "import sys,numpy as np; np.load(sys.argv[1], allow_pickle=False).files" "$f" 2>/dev/null \
    || { echo "SHARD FILE IN THE OLD FORMAT: $f. Upload the converted files first (aws s3 cp data/shards/n4/ s3://BUCKET/shards/n4/ --recursive, then sync them down on this host). Nothing was restarted."; exit 1; }
done
systemctl daemon-reload
systemctl restart genkart-shard@0 genkart-shard@1 genkart-shard@2 genkart-shard@3
[ -x /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl ] || dnf install -y -q amazon-cloudwatch-agent > /dev/null
cp shard-agent.json /opt/aws/amazon-cloudwatch-agent/etc/shard-agent.json
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/shard-agent.json -s > /dev/null
sleep 12
for i in 0 1 2 3; do
  if ! systemctl is-active --quiet "genkart-shard@$i"; then echo "NOT ACTIVE: genkart-shard@$i"; journalctl -u "genkart-shard@$i" -n 6 --no-pager | cut -c1-200; tail -15 "/var/log/genkart/shard-$i.log" 2>/dev/null; exit 1; fi
  echo "active: genkart-shard@$i"
done
systemctl is-active --quiet amazon-cloudwatch-agent && echo "active: amazon-cloudwatch-agent"
for p in 9101 9102 9103 9104; do curl -sf --max-time 3 localhost:$p/health || { echo "shard on $p does not answer"; exit 1; }; echo; done
ls -l /var/log/genkart/
echo "UPDATE OK"
