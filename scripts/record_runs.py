"""Record real pipeline runs for the public Viewer: web/src/recorded/runs.json (no photos, closed catalogues anonymised).

Runs each chosen prompt through the running local web server (so the real model, graph, catalogues and, if it is up, the router answer),
keeps the streamed events with their real timings, makes them publishable with genkart.recording, and attaches the author's blind rating
of the RAW search for that prompt from test set 5. The page runs the full pipeline, which the blind tests found no better than raw search,
so a recorded result can differ from the one that was rated: the Viewer says so.
Usage: .venv/bin/python scripts/record_runs.py "AWS Mumbai (ap-south-1)" [http://127.0.0.1:8000]   (the first argument says where the search ran; server must be running; needs data/ and Ollama)
"""
import datetime
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, "src")
from genkart.recording import photo_map, photo_map_plain, rating_for, sanitize_events, sanitize_plain  # noqa: E402

WHERE = sys.argv[1]          # stated by the person recording: "router" alone does not say whether it was AWS or the local cluster
BASE = sys.argv[2].rstrip("/") if len(sys.argv) > 2 else "http://127.0.0.1:8000"
# 4 rated good, 1 okay, 3 bad by the author (blind, raw search): chosen by variety of request, not by how the results look
PROMPTS = [
    "Haldi ceremony outfit for bride's brother, yellow kurta with white pyjama",
    "Karva Chauth look, red or maroon saree with heavy border",
    "Kids ethnic wear for 5 year old boy for Diwali puja, kurta with jacket",
    "Christmas dinner dress for women, green or red velvet, knee length",
    "Engagement ring ceremony groom, sherwani in ivory with stole",
    "Winter wedding in Delhi, women's velvet suit with shawl",
    "Sangeet night for groom, indo-western jacket with kurta, royal blue",
    "Gujarati garba dandiya men, kediyu and churidar set, colourful",
]

lines = pathlib.Path("data/human_prompts_test5.txt").read_text().splitlines()
number = {text.strip(): i for i, text in enumerate([l for l in lines if l.strip() and not l.startswith("#")], 1)}
ratings = json.load(open("data/human_ratings_test5.json"))
key = json.load(open("data/preview/blind_key5.json"))
health = json.load(urllib.request.urlopen(f"{BASE}/api/health", timeout=5))
if not health.get("ollama"):
    sys.exit("Ollama is not running: the understand step would be recorded as a failure. Start it first.")

runs, photos = [], {}
for text in PROMPTS:
    n = number[text]
    t0 = time.time()
    events = []
    for raw in urllib.request.urlopen(f"{BASE}/api/search?{urllib.parse.urlencode({'q': text})}", timeout=600):
        raw = raw.decode().strip()
        if raw.startswith("data: "):
            events.append(json.loads(raw[6:]))
    bad = [e["stage"] for e in events if e.get("kind") == "step" and e["status"] == "failed"]
    if bad or not events or events[-1].get("kind") != "end":
        sys.exit(f"not recorded: '{text}' had failed steps {bad} or did not finish; fix the cause and run again (nothing was written)")
    safe = sanitize_events(events)
    photos.update(photo_map(events, safe))
    plain = json.load(urllib.request.urlopen(f"{BASE}/api/plain?{urllib.parse.urlencode({'q': text})}", timeout=120))   # the same sentence searched as typed, no plan
    plain_safe = sanitize_plain(plain["hits"])
    photos.update(photo_map_plain(plain["hits"], plain_safe))
    runs.append({"id": f"t5-p{n}", "prompt": text, "test_set": 5, "prompt_no": n, "author_rating_of_raw_search": rating_for(n, ratings, key, "B"), "author_rating_of_plan": rating_for(n, ratings, key, "C"),
                 "plain": {"seconds": plain["seconds"], "hits": plain_safe},
                 "wall_seconds": round(time.time() - t0, 2), "events": safe})
    print(f"p{n} {runs[-1]['author_rating_of_raw_search']:>5}  {runs[-1]['wall_seconds']:>6} s  {text}")

snap = json.load(urllib.request.urlopen(f"{BASE}/api/resources", timeout=10))   # memory actually held by the recording computer right after the runs (measured, not estimated)
out = {"recorded_at": datetime.date.today().isoformat(), "where": WHERE, "resources": {"measured": "right after the 8 runs, on the computer that recorded them", **snap},
       "understand_model": "qwen3:4b-instruct", "note": "No photos. Product ids and titles only for the Marqo catalogue.", "runs": runs}
path = pathlib.Path("web/src/recorded/runs.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, indent=1))
pathlib.Path("data/run").mkdir(parents=True, exist_ok=True)
pathlib.Path("data/run/recorded_photo_ids.json").write_text(json.dumps(photos))   # local only (data/ is never committed)
print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
