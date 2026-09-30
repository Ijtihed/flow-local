"""Linux settings, served on loopback with an unguessable session path."""
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

import paths

METHODS = {"stamp", "history", "delete", "clear", "copy", "edit", "settings", "save_settings",
           "insights", "memory", "add_term", "remove_term", "remove_fix", "scan_vaults",
           "enable_voice_notes", "system", "setup_run", "setup_status", "finish_onboarding",
    "configure_speech", "forget_api_key", "recording_status", "record_start", "record_stop", "record_cancel",
    "practice_open", "practice_start", "practice_stop", "practice_cancel", "practice_status", "practice_complete"}


def make_server(api):
    token = secrets.token_urlsafe(32)
    prefix = "/" + token + "/"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, payload, mime="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(payload)

        def allowed(self):
            host = f"127.0.0.1:{self.server.server_port}"
            return (self.headers.get("Host") == host
                    and self.headers.get("Origin", "http://" + host) == "http://" + host
                    and urlsplit(self.path).path.startswith(prefix))

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, b'{}')
            rel = urlsplit(self.path).path[len(prefix):]
            if rel in ("", "ui.html"):
                html = (paths.APP / "ui.html").read_text("utf-8")
                bridge = '''<script>
                window.pywebview = {api: new Proxy({}, {get: (_, method) => async (...args) => {
                  const response = await fetch('api/' + method, {method: 'POST',
                    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(args)});
                  const result = await response.json();
                  if (!response.ok) throw new Error(result.error || 'Request failed');
                  return result;
                }})};
                </script>'''
                return self.respond(200, html.replace("<head>", "<head>" + bridge).encode(), "text/html; charset=utf-8")
            asset = (paths.APP / rel).resolve()
            if not rel.startswith("assets/") or not asset.is_relative_to((paths.APP / "assets").resolve()) or not asset.is_file():
                return self.respond(404, b'{}')
            import mimetypes
            self.respond(200, asset.read_bytes(), mimetypes.guess_type(str(asset))[0] or "application/octet-stream")

        def do_POST(self):
            if not self.allowed() or not self.path.startswith(prefix + "api/"):
                return self.respond(403, b'{}')
            method = self.path[len(prefix + "api/"):]
            if method not in METHODS:
                return self.respond(404, b'{}')
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 1_000_000 or self.headers.get("Content-Type") != "application/json":
                    return self.respond(400, b'{}')
                args = json.loads(self.rfile.read(size))
                if not isinstance(args, list):
                    return self.respond(400, b'{}')
                result = getattr(api, method)(*args)
                self.respond(200, json.dumps(result, ensure_ascii=False).encode())
            except Exception as ex:
                self.respond(400, json.dumps({"error": str(ex)}).encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    return server, f"http://127.0.0.1:{server.server_port}{prefix}"


def serve(api):
    server, url = make_server(api)
    print("Flow Settings:", url, flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
