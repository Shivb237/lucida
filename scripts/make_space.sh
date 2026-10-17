#!/bin/bash
# Assemble the folder that is built into the hosted Lab's Docker image: space-build/. Nothing here is committed to this repository.
# Marqo photos are NOT copied (the image build fetches them from Marqo's dataset, space/Dockerfile); the other catalogues' thumbnails ARE copied in. Needs the local data/ folder (index, titles) and Node for the page build.
# Usage: scripts/make_space.sh      then:  cd space-build && gcloud builds submit --tag <registry>/<repo>/lab:<n> --timeout=3600 .   and   gcloud run deploy (see README)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-space-build}"      # another folder name lets a second build be prepared while the first is still being uploaded
rm -rf "$OUT" && mkdir -p "$OUT/data/index" "$OUT/data/sample_scale" "$OUT/data/clean" "$OUT/data/raw" "$OUT/scripts" "$OUT/web"
(cd web && npm ci --silent && npm run build)                       # the Lab page (not the Viewer-only build)
cp -R space/. "$OUT/"
cp -R src "$OUT/src" && find "$OUT/src" -name __pycache__ -prune -exec rm -rf {} +
cp scripts/space_fetch_photos.py "$OUT/scripts/"
cp -R web/dist "$OUT/web/dist"
for n in scale kaggle myntra2 mens3; do cp "data/index/$n-marqo-fashionsiglip.npz" "data/index/$n-marqo-fashionsiglip.meta.json" "$OUT/data/index/"; done   # all four catalogues
mkdir -p "$OUT/data/kaggle" "$OUT/data/images"
cp data/kaggle/styles.csv "$OUT/data/kaggle/"                                  # titles, genders and the knowledge graph
python3 - "$OUT" <<'PY'
import json, sys
lab = json.load(open("data/clean/mens3_labels.json"))
json.dump({k: {"title": v["title"]} for k, v in lab.items()}, open(sys.argv[1] + "/data/clean/mens3_labels.json", "w"))   # titles only: no local file paths
PY
.venv/bin/python scripts/make_space_photos.py "$OUT/data/images"               # thumbnails of the Kaggle, Myntra and men's photos (the Marqo ones are fetched by the image build)
cp data/sample_scale/products.jsonl "$OUT/data/sample_scale/"
cp data/clean/dup_clusters_4.json data/clean/manual_flags.json "$OUT/data/clean/"
cp data/raw/MANIFEST_scale.json "$OUT/data/raw/"
# the study's 20 prompts (the ones the Stable Diffusion drawings were made for): ids and texts only
mkdir -p "$OUT/data/study"
python3 - "$OUT" <<'PY'
import json, sys
rows = [json.loads(l) for l in open("runs/gen_sd15.jsonl")]
json.dump([{"query_id": r["query_id"], "query": r["query"]} for r in rows], open(sys.argv[1] + "/data/study/prompts.json", "w"))
PY
# Viewer replay on the hosted Lab: published id -> real id (every catalogue's photos are in the image now)
mkdir -p "$OUT/data/run"
cp data/run/recorded_photo_ids.json "$OUT/data/run/"
echo "built $OUT: $(du -sh "$OUT" | cut -f1), $(find "$OUT" -type f | wc -l) files"
