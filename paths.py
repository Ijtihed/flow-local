"""Where Flow keeps things. Installed: code in Program Files-style folder, data in %APPDATA%\\Flow."""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
APP = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))   # read-only: ui.html, assets/
DATA = Path(os.environ.get("FLOW_DATA") or Path(os.environ.get("APPDATA", Path.home())) / "Flow")
HISTORY = DATA / "history.jsonl"
SETTINGS = DATA / "settings.json"
MEMORY = DATA / "memory.db"
MODELS = DATA / "models"
CUDA = DATA / "cuda"
ICON = APP / "assets" / "flow.ico"

DEFAULT_STYLES = {"personal": "very casual", "work": "casual", "email": "formal", "ai": "very casual",
                  "code": "casual", "docs": "formal", "other": "casual"}
DEFAULTS = {"shortcut": "ctrl+win", "styles": DEFAULT_STYLES, "languages": ["en"], "snippets": [],
            "cleanup": True, "learn": True, "texting": True, "model": "large-v3", "name": "",
            "voice_notes": {"enabled": False, "folder": ""}, "onboarded": False}


def load_settings():
    import json
    try:
        s = json.loads(SETTINGS.read_text("utf-8"))
    except Exception:
        s = {}
    out = {**DEFAULTS, **s}
    # older versions had one chat style and one for everything else
    if "style_chat" in s or "style_other" in s:
        out["styles"] = {**DEFAULT_STYLES, **{k: v for k, v in (("personal", s.get("style_chat")),
                                                              ("other", s.get("style_other"))) if v}}
    out["styles"] = {**DEFAULT_STYLES, **out.get("styles", {})}
    out["voice_notes"] = {**DEFAULTS["voice_notes"], **(out.get("voice_notes") or {})}
    return out


def save_settings(patch):
    import json
    cur = load_settings()
    cur.update(patch)
    cur.pop("style_chat", None)
    cur.pop("style_other", None)
    DATA.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(cur, indent=2, ensure_ascii=False), "utf-8")
    return cur


def launch_command(*args):
    """How to start another Flow process (the window), frozen or from source."""
    if FROZEN:
        return [sys.executable, *args]
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pyw if pyw.exists() else sys.executable), str(APP / "main.py"), *args]
