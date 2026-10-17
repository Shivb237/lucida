"""Download two parquet shards of Marqo-GS-10M (about 0.2 GB each) for the pilot sample, and record exactly what was fetched.

The dataset is 212 GB in total; we only need a small, reproducible slice. The manifest stores the dataset revision (git
sha on the Hub) and the sha256 of each shard, so anyone can verify they have the same data.
Usage: .venv/bin/python scripts/fetch_pilot_shards.py
"""
import hashlib
import json
import pathlib

from huggingface_hub import HfApi, hf_hub_download

REPO = "Marqo/marqo-GS-10M"
SHARDS = ["data/in_domain-168.parquet", "data/in_domain-157.parquet"]  # chosen because they sampled as apparel-heavy
OUT = pathlib.Path("data/raw")
OUT.mkdir(parents=True, exist_ok=True)

info = HfApi().dataset_info(REPO)
manifest = {"repo": REPO, "revision": info.sha, "license": "apache-2.0 (dataset card); cite Zhu et al. 2024, arXiv:2404.08535", "files": []}
for name in SHARDS:
    path = pathlib.Path(hf_hub_download(REPO, name, repo_type="dataset", revision=info.sha, local_dir=OUT))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["files"].append({"name": name, "bytes": path.stat().st_size, "sha256": sha})
    print(f"{name}: {path.stat().st_size/1e6:.0f} MB  sha256 {sha[:16]}...")
(OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
print("revision:", info.sha)
