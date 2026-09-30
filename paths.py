"""Application assets are read-only; user data lives in APPDATA on Windows or XDG_DATA_HOME on Linux."""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
APP = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))   # read-only: ui.html, assets/
_default_data = (Path(os.environ.get("APPDATA", Path.home())) / "Flow" if sys.platform == "win32"
                 else Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "flow")
DATA = Path(os.environ.get("FLOW_DATA") or _default_data)
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
DEFAULTS.update({"speech_provider": "local", "api_model": "gpt-transcribe",
                 "api_base": "https://api.openai.com/v1", "api_consent": False,
                 "mood": "auto", "tutorial_seen": False, "auto_update": True})


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
    import tempfile
    cur = load_settings()
    cur.update(patch)
    cur.pop("style_chat", None)
    cur.pop("style_other", None)
    DATA.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=DATA, prefix="settings-",
                                     suffix=".tmp", delete=False) as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
        tmp = Path(f.name)
    try:
        tmp.replace(SETTINGS)
    finally:
        tmp.unlink(missing_ok=True)
    return cur


def launch_command(*args):
    """How to start another Flow process (the window), frozen or from source."""
    if sys.platform.startswith("linux") and os.environ.get("APPIMAGE"):
        return [os.environ["APPIMAGE"], *args]
    if FROZEN:
        return [sys.executable, *args]
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pyw if pyw.exists() else sys.executable), str(APP / "main.py"), *args]
