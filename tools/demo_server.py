"""Example-only product preview. No microphone, profile, model, credentials or OS controls.

Used for the documentation's first-dictation GIF. Open the printed URL in a browser.
"""
import argparse
import datetime
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths
from ui_linux import make_server
from version import APP_VERSION


class Demo:
    def __init__(self, practice=False):
        self.values = {**paths.DEFAULTS, "name": "Alex", "onboarded": True, "tutorial_version": 0 if practice else 2,
            "version": APP_VERSION, "platform": "windows", "native_window": False, "model": "small",
            "speech_models": [{"id": "small", "gb": .5, "ready": True, "supported": True}],
            "recommended_model": "small", "gpu": None, "cuda": False, "api_key_saved": False,
            "ollama": {"running": False, "model": False}}
        self.opened = None
        self.finished = False
    def settings(self): return self.values
    def memory(self): return {"terms": [], "fixes": [], "scanned": None}
    def stamp(self): return 1
    def history(self): return []
    def insights(self): return {"words": 0, "minutes_saved": 0, "wpm": 0, "apps": [], "known": 0, "sessions": 0}
    def diagnostics(self): return {"status": "passed", "version": APP_VERSION}
    def update_status(self): return {"phase": "current", "current": APP_VERSION, "publisher": False}
    def recording_status(self): return {"ready": True, "phase": "idle", "recording": False, "busy": False}
    def practice_open(self, focused=True):
        self.opened = time.monotonic()
        return {"id": "a"*32, "phrase": "I can speak instead of typing.", "api": False}
    def practice_focus(self, focused): return True
    def practice_close(self): return True
    def practice_status(self, focused=True):
        elapsed = time.monotonic() - (self.opened or time.monotonic())
        phase = "ready" if elapsed < 2 else "recording" if elapsed < 4.8 else "thinking" if elapsed < 5.8 else "passed"
        result = {"phase": phase, "ready": True, "matched": phase == "passed", "elapsed": elapsed}
        if phase == "passed": result["text"] = "I can speak instead of typing."
        return result
    def practice_complete(self):
        if self.practice_status()["phase"] != "passed": raise ValueError("The demo has not finished.")
        self.values["tutorial_version"] = 2
        return True
    def mcp_connection(self, read_only=False):
        return {"json": {"mcpServers": {"flow": {"command": "FlowMCP.exe", "args": ["--read-only"] if read_only else []}}}}
    def copy_mcp_connection(self, format="json", read_only=False): return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--practice", action="store_true")
    args = parser.parse_args()
    server, url = make_server(Demo(args.practice))
    print(url, flush=True)
    server.serve_forever()
