#!/bin/bash
# Packs the code the AWS machines need into data/deploy/ (git-ignored): one .tgz per program, the CPU torch lock (requirements-torch-cpu.txt)
# and MANIFEST.sha256. Nothing secret, no data files. It does not upload anything and prints no upload commands: those are in infra/README.md
# (Deploy, step 4; the unit files, other requirements locks and agent configs go up from deploy/ and infra/cloudwatch/ directly).
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
# the router ships compiled (dist/, plain JavaScript) so the machine's Node 22+ runs it without TypeScript support; its tests run first
# (the tests import .ts files: they need a Node that strips types by default, 22.18+ or 23.6+; CI uses Node 24 LTS. An older Node only
# typechecks and builds, and says so)
if node -e 'process.exit(process.features.typescript ? 0 : 1)'; then ROUTER_TEST="npm test --silent"; else ROUTER_TEST="true"; echo "router tests skipped: node $(node --version) cannot run .ts (use Node 24 LTS: see services/router)"; fi
( cd services/router && npm ci --silent && npm run -s typecheck && $ROUTER_TEST > /dev/null && rm -rf dist && npm run -s build ) || { echo "ROUTER BUILD OR TESTS FAIL: not packaging"; exit 1; }
tar -czf data/deploy/genkart-router-src.tgz -C services/router package.json dist
tmp=$(mktemp -d); tar -xzf data/deploy/genkart-router-src.tgz -C "$tmp"
node --input-type=module -e "await import('$tmp/dist/server.js'); await import('$tmp/dist/config.js')" || { echo "PACKAGE BROKEN: genkart-router-src.tgz cannot load dist/server.js on its own"; rm -rf "$tmp"; exit 1; }
rm -rf "$tmp"; echo "package self-test ok: router (dist/server.js)"
# test what we ship, not the working tree: unpack each package into an EMPTY folder and import its entry module (a forgotten file fails here, on the Mac)
for spec in "shard:genkart.shard_worker" "encoder:genkart.encoder_service genkart.embed" "ingest:genkart.ingest_worker genkart.sqs_queue"; do
  name="${spec%%:*}"; mods="${spec#*:}"; tmp=$(mktemp -d)
  tar -xzf "data/deploy/genkart-$name-src.tgz" -C "$tmp" 2>/dev/null
  for m in $mods; do
    ( cd "$tmp" && PYTHONPATH="$tmp/src" "$OLDPWD/.venv/bin/python" -c "import $m" ) || { echo "PACKAGE BROKEN: genkart-$name-src.tgz cannot import $m on its own"; rm -rf "$tmp"; exit 1; }
  done
  rm -rf "$tmp"; echo "package self-test ok: $name ($mods)"
done
# the router host installs CPU torch from this lock (hash-checked) before the encoder lock: it travels with the packages
cp space/requirements-torch-cpu.txt data/deploy/
grep -q 'sha256:' data/deploy/requirements-torch-cpu.txt || { echo "TORCH LOCK HAS NO HASHES: run scripts/lock.sh"; exit 1; }
for f in data/deploy/*.tgz; do echo "$f: $(tar -tzf "$f" | wc -l | tr -d ' ') files, $(wc -c < "$f" | tr -d ' ') bytes"; done
echo "secret-like words inside the packages (expect 0):"; for f in data/deploy/*.tgz; do tar -xzOf "$f" | grep -ciE "sk-ant|AKIA|api_key|password" || true; done | paste -sd' ' -
( cd data/deploy && shasum -a 256 *.tgz requirements-torch-cpu.txt > MANIFEST.sha256 ) && echo "manifest: data/deploy/MANIFEST.sha256 (sha256 of every package, upload it with them)"
