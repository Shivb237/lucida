#!/bin/bash
# Packs what the AWS machines need into data/deploy/ (git-ignored) and lists the upload commands. Nothing secret, no data files.
# Usage: scripts/package_shard_code.sh
set -euo pipefail
export COPYFILE_DISABLE=1   # no macOS extended-attribute noise inside the tar files
cd "$(dirname "$0")/.."
mkdir -p data/deploy
# never ship code that does not pass its tests (the working tree may hold half-finished edits)
.venv/bin/python -m pytest -q tests > /dev/null || { echo "TESTS FAIL: not packaging"; exit 1; }
tar --exclude='__pycache__' -czf data/deploy/genkart-shard-src.tgz \
  src/genkart/__init__.py src/genkart/shard_worker.py src/genkart/sharding.py src/genkart/catalogue.py src/genkart/dedup.py src/genkart/index.py src/genkart/reqlog.py
tar --exclude='__pycache__' -czf data/deploy/genkart-encoder-src.tgz src/genkart/__init__.py src/genkart/embed.py src/genkart/encoder_service.py src/genkart/reqlog.py src/genkart/admission.py
tar --exclude='__pycache__' -czf data/deploy/genkart-ingest-src.tgz src/genkart/__init__.py src/genkart/ingest_worker.py src/genkart/sqs_queue.py src/genkart/jobqueue.py
tar --exclude='__pycache__' --exclude='node_modules' -czf data/deploy/genkart-router-src.tgz -C services/router package.json src
# test what we ship, not the working tree: unpack each package into an EMPTY folder and import its entry module (a forgotten file fails here, on the Mac)
for spec in "shard:genkart.shard_worker" "encoder:genkart.encoder_service genkart.embed" "ingest:genkart.ingest_worker genkart.sqs_queue"; do
  name="${spec%%:*}"; mods="${spec#*:}"; tmp=$(mktemp -d)
  tar -xzf "data/deploy/genkart-$name-src.tgz" -C "$tmp" 2>/dev/null
  for m in $mods; do
    ( cd "$tmp" && PYTHONPATH="$tmp/src" "$OLDPWD/.venv/bin/python" -c "import $m" ) || { echo "PACKAGE BROKEN: genkart-$name-src.tgz cannot import $m on its own"; rm -rf "$tmp"; exit 1; }
  done
  rm -rf "$tmp"; echo "package self-test ok: $name ($mods)"
done
for f in data/deploy/*.tgz; do echo "$f: $(tar -tzf "$f" | wc -l | tr -d ' ') files, $(wc -c < "$f" | tr -d ' ') bytes"; done
echo "secret-like words inside the packages (expect 0):"; for f in data/deploy/*.tgz; do tar -xzOf "$f" | grep -ciE "sk-ant|AKIA|api_key|password" || true; done | paste -sd' ' -
( cd data/deploy && shasum -a 256 *.tgz > MANIFEST.sha256 ) && echo "manifest: data/deploy/MANIFEST.sha256 (sha256 of every package, upload it with them)"
