#!/bin/bash
# Assemble the folder that is built into the hosted Lab's Docker image: space-build/. Nothing here is committed to this repository.
# Photos are NOT copied: the image build fetches them from Marqo's dataset (space/Dockerfile). Needs the local data/ folder (index, titles) and Node for the page build.
# Usage: scripts/make_space.sh      then:  cd space-build && gcloud builds submit --tag <registry>/<repo>/lab:<n> --timeout=3600 .   and   gcloud run deploy (see README)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=space-build
rm -rf "$OUT" && mkdir -p "$OUT/data/index" "$OUT/data/sample_scale" "$OUT/data/clean" "$OUT/data/raw" "$OUT/scripts" "$OUT/web"
(cd web && npm ci --silent && npm run build)                       # the Lab page (not the Viewer-only build)
cp -R space/. "$OUT/"
cp -R src "$OUT/src" && find "$OUT/src" -name __pycache__ -prune -exec rm -rf {} +
cp scripts/space_fetch_photos.py "$OUT/scripts/"
cp -R web/dist "$OUT/web/dist"
cp data/index/scale-marqo-fashionsiglip.npz data/index/scale-marqo-fashionsiglip.meta.json "$OUT/data/index/"
cp data/sample_scale/products.jsonl "$OUT/data/sample_scale/"
cp data/clean/dup_clusters_4.json data/clean/manual_flags.json "$OUT/data/clean/"
cp data/raw/MANIFEST_scale.json "$OUT/data/raw/"
# Viewer replay on the hosted Lab: published id -> real id, kept only where the photo is in the image (Marqo ones; Kaggle/Myntra photos are local-only by licence)
mkdir -p "$OUT/data/run"
python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]
have = {int(json.loads(l)["product_id"]) for l in open(f"{out}/data/sample_scale/products.jsonl")}
m = json.load(open("data/run/recorded_photo_ids.json"))
json.dump({k: v for k, v in m.items() if int(v) in have}, open(f"{out}/data/run/recorded_photo_ids.json", "w"))
PY
echo "built $OUT: $(du -sh "$OUT" | cut -f1), $(find "$OUT" -type f | wc -l) files"
