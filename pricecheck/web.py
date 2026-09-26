"""Loopback-only price comparison page. One search at a time; credentials stay server-side."""

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from jev_ultrafast.demo import load_environment

from .compare import compare
from .shops import BY_KEY, SHOPS

ROOT = Path(__file__).parent / "static"
PORT = int(os.environ.get("PRICECHECK_PORT", "8767"))
ORIGIN = f"http://127.0.0.1:{PORT}"
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
STATE = {"running": False, "product": None, "progress": {}, "report": None, "error": None}


def public_state():
    with LOCK:
        return json.loads(json.dumps({**STATE, "shops": [{"key": s["key"], "name": s["name"]} for s in SHOPS]}))


def search(product, shops, runner=compare):
    def progress(update):
        with LOCK:
            STATE["progress"][update["shop"]] = f"{update['agent_status']} · {update['actions']} actions"

    try:
        report = runner(product, shops, on_update=progress)
        with LOCK:
            STATE.update(report=report)
    except Exception as error:  # noqa: BLE001
        with LOCK:
            STATE.update(error=str(error)[:300] or "Search failed")
    finally:
        with LOCK:
            STATE["running"] = False


def start(body, runner=compare):
    if not isinstance(body, dict):
        raise ValueError("Invalid request")
    product = str(body.get("product", "")).strip()
    if not product or len(product) > 120:
        raise ValueError("Enter a product name of 1–120 characters")
    keys = body.get("shops") or [s["key"] for s in SHOPS]
    if not isinstance(keys, list) or not keys or any(k not in BY_KEY for k in keys):
        raise ValueError("Unknown shop")
    with LOCK:
        if STATE["running"]:
            raise ValueError("A search is already running")
        STATE.update(running=True, product=product, report=None, error=None,
                     progress={k: "waiting" for k in keys})
    threading.Thread(target=search, args=(product, [BY_KEY[k] for k in keys], runner), daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, mime="application/json"):
        content = content if isinstance(content, bytes) else content.encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.headers.get("Host") != f"127.0.0.1:{PORT}":
            return self.send(403, "Forbidden", "text/plain")
        path = urlparse(self.path).path
        if path == "/api/state":
            return self.send(200, json.dumps(public_state()))
        files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                 "/style.css": ("style.css", "text/css")}
        if path not in files:
            return self.send(404, "Not found", "text/plain")
        name, mime = files[path]
        self.send(200, (ROOT / name).read_text().replace("__TOKEN__", TOKEN), mime + "; charset=utf-8")

    def do_POST(self):
        if (
            self.headers.get("Host") != f"127.0.0.1:{PORT}"
            or self.headers.get("X-Demo-Token") != TOKEN
            or self.headers.get("Origin") not in (None, ORIGIN)
            or urlparse(self.path).path != "/api/search"
        ):
            return self.send(403, json.dumps({"error": "Local requests only"}))
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 4096:
                raise ValueError("Invalid request size")
            start(json.loads(self.rfile.read(length)))
            self.send(200, json.dumps(public_state()))
        except ValueError as error:
            self.send(400, json.dumps({"error": str(error)}))

    def log_message(self, *_args):
        pass


def main():
    load_environment()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Price check: {ORIGIN}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
