#!/bin/bash
# Run ON the router host, as root. Switches the overload-handling variant being measured, without rebuilding anything:
#   baseline  encoder starts every request at once, router has no limit            (what we had)
#   v1        encoder gate of 2 + deadlines (abandoned work is dropped)             ENCODER_CONCURRENCY=2
#   v2        v1 + the router answers 429 "busy" past 12 searches in flight         MAX_INFLIGHT=12
# Usage: set-variant.sh baseline|v1|v2
set -euo pipefail
V="${1:-}"
case "$V" in
  baseline) CONC=0; MAXIN=0 ;;
  v1)       CONC=2; MAXIN=0 ;;
  v2)       CONC=2; MAXIN=12 ;;
  *) echo "usage: $0 baseline|v1|v2"; exit 2 ;;
esac
echo "ENCODER_CONCURRENCY=$CONC" > /etc/genkart/encoder.env
sed -i '/^MAX_INFLIGHT=/d' /etc/genkart/router.env
echo "MAX_INFLIGHT=$MAXIN" >> /etc/genkart/router.env
systemctl daemon-reload
systemctl restart genkart-encoder genkart-router
for i in $(seq 1 40); do                      # the encoder needs about a minute to load its model
  if curl -sf --max-time 3 http://127.0.0.1:9100/health | grep -q '"encoder":true'; then break; fi; sleep 5
done
curl -sf --max-time 3 http://127.0.0.1:9100/health | grep -q '"encoder":true' || { echo "router/encoder did not come back"; tail -5 /var/log/genkart/encoder.log; exit 1; }
echo "variant $V active: $(cat /etc/genkart/encoder.env), $(grep MAX_INFLIGHT /etc/genkart/router.env)"
