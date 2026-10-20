#!/bin/zsh
# Start / stop / status of the local cluster: encoder (9000), shard workers, router (9100). PIDs in data/run/.
# Replicas: REPLICAS=2 (default) runs each shard twice: replica A on 9101-9104, replica B on 9111-9114. REPLICAS=1 runs one worker per shard.
# SHARDS_DIR=data/shards/n4h to use the shard files with held-out products.
# MAX_INFLIGHT: the router's load-shedding limit. 0 (the default HERE) = no limit: this is the experiment cluster, and scripts/chaos.py's
# load phase (up to 64 clients at once) must measure the system, not 429 "busy" answers. The router's own default (12) is what the AWS
# host runs; MAX_INFLIGHT=12 scripts/cluster.sh start reproduces it.
# Usage: [REPLICAS=1] [SHARDS_DIR=..] [MAX_INFLIGHT=n] scripts/cluster.sh start|stop|status
cd "$(dirname "$0")/.."
mkdir -p data/run
REPLICAS=${REPLICAS:-2}
SHARDS_DIR=${SHARDS_DIR:-data/shards/n4}
MAX_INFLIGHT=${MAX_INFLIGHT:-0}
case "$1" in
  start)
    export GENKART_ADMIN=1   # local fault-injection route for the chaos scripts; never set on AWS
    PYTHONPATH=src nohup .venv/bin/python -m genkart.encoder_service --port 9000 > data/run/encoder.log 2>&1 & echo $! > data/run/encoder.pid
    URLS=""
    for i in 0 1 2 3; do
      PYTHONPATH=src nohup .venv/bin/python -m genkart.shard_worker --shard $i --of 4 --dir $SHARDS_DIR --port $((9101+i)) > data/run/shard$i.log 2>&1 & echo $! > data/run/shard$i.pid
      GROUP="http://127.0.0.1:$((9101+i))"
      if [ "$REPLICAS" -ge 2 ]; then
        PYTHONPATH=src nohup .venv/bin/python -m genkart.shard_worker --shard $i --of 4 --dir $SHARDS_DIR --port $((9111+i)) > data/run/shard${i}b.log 2>&1 & echo $! > data/run/shard${i}b.pid
        GROUP="$GROUP|http://127.0.0.1:$((9111+i))"
      fi
      URLS="${URLS:+$URLS,}$GROUP"
    done
    # the compiled router (dist/) runs on any Node 22+; without node_modules (no `npm ci` yet) Node 24 LTS (or 22.18+) runs the TypeScript itself
    ROUTER_MAIN=src/index.ts
    if [ -x services/router/node_modules/.bin/tsc ]; then (cd services/router && npm run -s build) && ROUTER_MAIN=dist/index.js; fi
    (cd services/router && SHARD_URLS="$URLS" MAX_INFLIGHT="$MAX_INFLIGHT" nohup node $ROUTER_MAIN > ../../data/run/router.log 2>&1 & echo $! > ../../data/run/router.pid)
    echo "started with $REPLICAS replica(s) per shard, MAX_INFLIGHT=$MAX_INFLIGHT (0 = no limit); wait for: scripts/cluster.sh status" ;;
  stop)
    for f in data/run/*.pid(N); do
      pid="$(cat $f)"
      # a saved number can belong to an unrelated program after a reboot: kill it only if its command line is one of ours
      if ps -p "$pid" -o command= 2>/dev/null | grep -Eq "genkart\.|src/index\.ts|dist/index\.js"; then kill "$pid"; else echo "skip $f: pid $pid is not a genkart process"; fi
      rm -f "$f"
    done; echo stopped ;;
  status)
    for p in 9000 9101 9102 9103 9104 9111 9112 9113 9114 9100; do printf "%s: " $p; curl -s -m 2 http://127.0.0.1:$p/health || printf "down"; echo; done ;;
esac
