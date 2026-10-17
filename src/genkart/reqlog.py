"""One JSON log line per request, carrying the search's ticket number (the x-request-id header the router sends).

The router, the encoder and every shard worker write the same ticket number into their own logs, so one search can be followed across
machines with a single CloudWatch Logs Insights query:   filter req = "<ticket>" | sort @timestamp
Health checks are not logged (they would drown everything else). The ticket is cut to 64 characters and printed as JSON, so a hostile
header value cannot inject extra log lines.
"""
from __future__ import annotations

import json
import time


def install(app, service: str, **fields) -> None:
    @app.middleware("http")
    async def _request_log(request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        req = request.headers.get("x-request-id", "-")[:64]
        t = time.perf_counter()
        status = 500                                   # what is logged if the handler raises
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            print(json.dumps({"req": req, "svc": service, **fields, "path": request.url.path, "status": status,
                              "ms": round((time.perf_counter() - t) * 1000, 2)}), flush=True)
