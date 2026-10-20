"""The web server's call to the router: HTTP 429 means "busy, ask again shortly", not "the search failed"."""
import http.server
import threading

import pytest

from genkart import server


def _router(statuses, ports=None):
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"          # keep-alive, like the real router

        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length", 0)))
            code = statuses[min(len(seen), len(statuses) - 1)]
            seen.append(code)
            if ports is not None:
                ports.append(self.client_address[1])
            body = b'{"results": []}' if code == 200 else b'{"error": "busy"}'
            self.send_response(code)
            self.send_header("retry-after", "0")
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)      # a thread per connection: a kept-alive one must not block shutdown()
    srv.daemon_threads = True
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
    import httpx
    srv, seen = _router([500])
    try:
        with pytest.raises(httpx.HTTPStatusError):
            server._post_json(f"http://127.0.0.1:{srv.server_port}/search", {"text": "x"})
        assert seen == [500]
    finally:
        srv.shutdown()


def test_router_calls_share_one_kept_alive_connection():
    """Every piece of every search goes through one shared client: the second call reuses the first one's connection (same client port),
    and a 429 retry does too. Before, each piece opened a new connection."""
    import httpx

    ports = []
    srv, seen = _router([200, 429, 200], ports)
    try:
        client = httpx.Client()
        url = f"http://127.0.0.1:{srv.server_port}/search"
        assert server._post_json(url, {"text": "x"}, client=client) == {"results": []}
        assert server._post_json(url, {"text": "y"}, client=client) == {"results": []}       # 429, then 200
        assert seen == [200, 429, 200] and len(set(ports)) == 1
        assert server._router_http() is server._router_http()                               # the default is one client for the whole process
    finally:
        srv.shutdown()


def test_the_timeout_still_applies():
    import httpx

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), type("Slow", (http.server.BaseHTTPRequestHandler,), {
        "do_POST": lambda self: __import__("time").sleep(1.0), "log_message": lambda self, *a: None}))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(httpx.TimeoutException):
            server._post_json(f"http://127.0.0.1:{srv.server_port}/search", {"text": "x"}, timeout=0.2, client=httpx.Client())
    finally:
        srv.shutdown()
