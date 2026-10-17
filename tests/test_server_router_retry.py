"""The web server's call to the router: HTTP 429 means "busy, ask again shortly", not "the search failed"."""
import http.server
import threading

import pytest

from genkart import server


def _router(statuses):
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length", 0)))
            code = statuses[min(len(seen), len(statuses) - 1)]
            seen.append(code)
            self.send_response(code)
            self.send_header("retry-after", "0")
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"results": []}' if code == 200 else b'{"error": "busy"}')

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def test_one_429_is_retried_and_the_second_answer_is_used():
    srv, seen = _router([429, 200])
    try:
        assert server._post_json(f"http://127.0.0.1:{srv.server_port}/search", {"text": "x"}) == {"results": []}
        assert seen == [429, 200]
    finally:
        srv.shutdown()


def test_two_429s_in_a_row_say_busy_in_plain_words():
    srv, seen = _router([429])
    try:
        with pytest.raises(RuntimeError, match="busy"):
            server._post_json(f"http://127.0.0.1:{srv.server_port}/search", {"text": "x"})
        assert seen == [429, 429]
    finally:
        srv.shutdown()


def test_other_errors_are_not_retried():
    import urllib.error
    srv, seen = _router([500])
    try:
        with pytest.raises(urllib.error.HTTPError):
            server._post_json(f"http://127.0.0.1:{srv.server_port}/search", {"text": "x"})
        assert seen == [500]
    finally:
        srv.shutdown()
