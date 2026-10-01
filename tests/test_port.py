"""Regression checks for OS wiring, key transitions and the loopback settings bridge."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hotkeys_linux import Hotkeys, SHORTCUTS
from ui_linux import make_server


class Keys(unittest.TestCase):
    def keyhook(self, shortcut="ctrl+win"):
        events = []
        h = Hotkeys.__new__(Hotkeys)
        h.emit = events.append
        h.groups = SHORTCUTS[shortcut]
        h.held = set()
        h.active = h.recording = False
        return h, events

    def test_hold_repeat_release(self):
        h, events = self.keyhook()
        for key, down in [("lctrl", True), ("rmeta", True), ("rmeta", True), ("rmeta", False), ("lctrl", False)]:
            h.handle(key, down)
        self.assertEqual(events, ["down", "up"])

    def test_lock_cancel_interrupt(self):
        h, events = self.keyhook("f8")
        h.handle("f8", True)
        h.recording = True
        h.handle("space", True)
        h.handle("esc", True)
        h.handle("left", True)
        h.handle("f8", False)
        self.assertEqual(events, ["down", "lock", "cancel", "interrupt", "up"])


class Bridge(unittest.TestCase):
    def setUp(self):
        class DemoApi:
            def settings(self): return {"platform": "linux", "name": "Alex"}
            def save_settings(self, patch): return patch
            def practice_focus(self, focused): return {"focused": focused}
            def practice_close(self): return {"closed": True}
        self.server, self.url = make_server(DemoApi())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_page_assets_and_rpc(self):
        with urlopen(self.url) as r:
            self.assertEqual(r.headers["X-Frame-Options"], "DENY")
            self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
            self.assertIn(b"window.pywebview", r.read())
        with urlopen(self.url + "assets/PlexSans-400.woff2") as r:
            self.assertEqual(r.read(4), b"wOF2")
        req = Request(self.url + "api/settings", data=b"[]", headers={"Content-Type": "application/json"})
        with urlopen(req) as r:
            self.assertEqual(json.load(r)["platform"], "linux")

    def assert_status(self, request, status):
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, status)

    def test_token_origin_host_and_path(self):
        base = self.url.split("/", 3)[:3]
        self.assert_status("/".join(base) + "/", 403)
        self.assert_status(Request(self.url, headers={"Host": "example.com"}), 403)
        self.assert_status(Request(self.url + "api/settings", data=b"[]", headers={"Origin": "https://example.com", "Content-Type": "application/json"}), 403)
        self.assert_status(self.url + "assets/../../paths.py", 404)

    def test_private_methods_and_invalid_args(self):
        self.assert_status(Request(self.url + "api/_memory", data=b"[]", headers={"Content-Type": "application/json"}), 404)
        self.assert_status(Request(self.url + "api/settings", data=b"{}", headers={"Content-Type": "application/json"}), 400)

    def test_tutorial_focus_and_close_rpc(self):
        for method, args, expected in (("practice_focus", [False], {"focused": False}),
                                       ("practice_focus", [True], {"focused": True}),
                                       ("practice_close", [], {"closed": True})):
            with self.subTest(method=method, args=args):
                req = Request(self.url + "api/" + method, data=json.dumps(args).encode(),
                              headers={"Content-Type": "application/json"})
                with urlopen(req) as r:
                    self.assertEqual(json.load(r), expected)


if __name__ == "__main__":
    unittest.main()
