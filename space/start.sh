#!/bin/sh
# the photos are already inside the image (fetched at build time): a start-up download would fill the host's in-memory disk
# a first search in the background loads the model into memory before a visitor arrives
(sleep 10; python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/plain?q=warm%%20up' % os.environ.get('PORT', '7860'), timeout=300).read()" >/dev/null 2>&1) &
exec python -m uvicorn genkart.server:app --app-dir src --host 0.0.0.0 --port ${PORT:-7860}
