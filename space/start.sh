#!/bin/sh
# the photos are already inside the image (fetched at build time): a start-up download would fill the host's in-memory disk
# the server loads the model, the catalogues and the knowledge graph itself as it starts, and /api/ready says when that is done. In the background:
# wait for it, then run one full search, so the code a first visitor's search goes through is loaded too (the page's first search used to pay for it)
(python - <<'PY'
import json, os, time, urllib.request
base = "http://127.0.0.1:%s" % os.environ.get("PORT", "7860")
for _ in range(600):
    try:
        urllib.request.urlopen(base + "/api/ready", timeout=5).read()
        break
    except Exception:
        time.sleep(1)
req = urllib.request.Request(base + "/api/search", data=json.dumps({"q": "warm up"}).encode(), headers={"content-type": "application/json"})
urllib.request.urlopen(req, timeout=300).read()
PY
) >/dev/null 2>&1 &
# exec: uvicorn becomes the main process and receives the host's stop signal itself (a clean shutdown instead of a kill after the grace period)
exec python -m uvicorn genkart.server:app --app-dir src --host 0.0.0.0 --port ${PORT:-7860}
