"""Price comparison page. Loopback-only by default; one search at a time; credentials stay server-side."""

import base64
import hmac
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
# A container binds 0.0.0.0 and names the Host headers it serves, e.g. "localhost:8767,prices.example.nl".
BIND = os.environ.get("PRICECHECK_BIND", "127.0.0.1")
HOSTS = {h.strip() for h in os.environ.get("PRICECHECK_ALLOWED_HOSTS", f"127.0.0.1:{PORT}").split(",") if h.strip()}
ORIGINS = {f"{scheme}://{host}" for host in HOSTS for scheme in ("http", "https")}
# Every search makes paid model calls. Set a password before exposing the page beyond this machine.
PASSWORD = os.environ.get("PRICECHECK_PASSWORD", "")
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


def authorized(header):
    if not PASSWORD:
        return True
    try:
        scheme, encoded = (header or "").split(" ", 1)
        _user, password = base64.b64decode(encoded).decode().split(":", 1)
    except ValueError:
        return False
    return scheme.lower() == "basic" and hmac.compare_digest(password.encode(), PASSWORD.encode())


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

    def allowed(self):
        if self.headers.get("Host") not in HOSTS:
            self.send(403, "Forbidden", "text/plain")
            return False
        if not authorized(self.headers.get("Authorization")):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Price Check", charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
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
        if not self.allowed():
            return
        if (
            self.headers.get("X-Demo-Token") != TOKEN
            or self.headers.get("Origin") not in (None, *ORIGINS)
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
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"Price check: {ORIGIN}" if BIND == "127.0.0.1" else f"Price check on {BIND}:{PORT} for {sorted(HOSTS)}",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
