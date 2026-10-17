"""Milestone 3: download 18 more Marqo-GS-10M shards (about 3.9 GB) for the scaled sample, and record exactly what was fetched.

The shards are drawn at random (seed 0) from the in_domain shards we do not already have, at the pinned dataset revision of the
pilot. The manifest (data/raw/MANIFEST_scale.json) stores each file's size and sha256. Shards from the pilot are listed too.
Usage: .venv/bin/python scripts/fetch_scale_shards.py
"""
import hashlib
import json
import pathlib
import random

from huggingface_hub import HfApi, hf_hub_download

REPO = "Marqo/marqo-GS-10M"
OUT = pathlib.Path("data/raw")
pilot = json.load(open(OUT / "MANIFEST.json"))
REVISION = pilot["revision"]  # same revision as the pilot, so the two samples come from identical data
have = {f["name"] for f in pilot["files"]}

info = HfApi().dataset_info(REPO, revision=REVISION, files_metadata=True)
sizes = {s.rfilename: s.size for s in info.siblings if s.rfilename.startswith("data/in_domain-")}
pool = sorted(k for k in sizes if k not in have)
picked = sorted(random.Random(0).sample(pool, 18))
print(f"downloading {len(picked)} shards, {sum(sizes[k] for k in picked)/1e9:.2f} GB, revision {REVISION[:8]}", flush=True)

manifest = {"repo": REPO, "revision": REVISION, "license": pilot["license"], "selection": "random.Random(0).sample of in_domain shards not in the pilot, 18 shards", "files": []}
for name in sorted(have) + picked:
    path = pathlib.Path(hf_hub_download(REPO, name, repo_type="dataset", revision=REVISION, local_dir=OUT))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["files"].append({"name": name, "bytes": path.stat().st_size, "sha256": sha, "from_pilot": name in have})
    print(f"{name}: {path.stat().st_size/1e6:.0f} MB sha256 {sha[:12]}", flush=True)
(OUT / "MANIFEST_scale.json").write_text(json.dumps(manifest, indent=2))
print("done; shards in manifest:", len(manifest["files"]))
