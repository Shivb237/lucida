"""Write web/src/recorded/photo-ids.json: the recorded products (published id -> real id) whose photos the hosted Lab serves.
The hosted Lab serves all four catalogues' photos, so every recorded product is included. Run after scripts/record_runs.py.
Usage: python scripts/export_viewer_photo_map.py"""
import json

m = json.load(open("data/run/recorded_photo_ids.json"))
json.dump(m, open("web/src/recorded/photo-ids.json", "w"), indent=0)
print(f"{len(m)} recorded products have a hosted photo")
