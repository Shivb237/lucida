#!/bin/zsh
# Start / stop / status of the local cluster: encoder (9000), shard workers, router (9100). PIDs in data/run/.
# Replicas: REPLICAS=2 (default) runs each shard twice: replica A on 9101-9104, replica B on 9111-9114. REPLICAS=1 runs one worker per shard.
# SHARDS_DIR=data/shards/n4h to use the shard files with held-out products. Usage: [REPLICAS=1] [SHARDS_DIR=..] scripts/cluster.sh start|stop|status
cd "$(dirname "$0")/.."
mkdir -p data/run
REPLICAS=${REPLICAS:-2}
SHARDS_DIR=${SHARDS_DIR:-data/shards/n4}
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
    (cd services/router && SHARD_URLS="$URLS" nohup node src/index.ts > ../../data/run/router.log 2>&1 & echo $! > ../../data/run/router.pid)
    echo "started with $REPLICAS replica(s) per shard; wait for: scripts/cluster.sh status" ;;
  stop)
    for f in data/run/*.pid(N); do
      pid="$(cat $f)"
      # a saved number can belong to an unrelated program after a reboot: kill it only if its command line is one of ours
      if ps -p "$pid" -o command= 2>/dev/null | grep -Eq "genkart\.|src/index\.ts"; then kill "$pid"; else echo "skip $f: pid $pid is not a genkart process"; fi
      rm -f "$f"
    done; echo stopped ;;
  status)
    for p in 9000 9101 9102 9103 9104 9111 9112 9113 9114 9100; do printf "%s: " $p; curl -s -m 2 http://127.0.0.1:$p/health || printf "down"; echo; done ;;
esac
