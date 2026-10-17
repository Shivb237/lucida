"""Write web/src/recorded/photo-ids.json: the recorded products whose photos the hosted Lab serves (the Marqo ones), published id -> real id.
Kaggle and Myntra photos are local-only by licence, so they are left out and stay placeholders. Run after scripts/record_runs.py.
Usage: python scripts/export_viewer_photo_map.py"""
import json

marqo = {int(json.loads(l)["product_id"]) for l in open("data/sample_scale/products.jsonl")}
m = json.load(open("data/run/recorded_photo_ids.json"))
keep = {k: v for k, v in m.items() if int(v) in marqo}
json.dump(keep, open("web/src/recorded/photo-ids.json", "w"), indent=0)
print(f"{len(keep)} of {len(m)} recorded products have a hosted photo")
