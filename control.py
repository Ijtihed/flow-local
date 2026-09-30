"""User-only local controls between the settings window and the speech tray."""
import json
import os
import re
import tempfile
import time
import unicodedata
import uuid
from pathlib import Path

import paths
from version import APP_VERSION

TUTORIAL_VERSION = 2
PHRASES = {
    "en": "I can speak instead of typing.",
    "fi": "Voin puhua kirjoittamisen sijaan.",
    "fr": "Je peux parler au lieu de taper.",
    "ar": "يمكنني التحدث بدلاً من الكتابة.",
    "sv": "Jag kan prata istället för att skriva.",
    "de": "Ich kann sprechen statt zu tippen.",
    "es": "Puedo hablar en lugar de escribir.",
    "it": "Posso parlare invece di scrivere.",
    "nl": "Ik kan praten in plaats van typen.",
    "pt": "Posso falar em vez de digitar.",
}


def phrase_for(settings):
    lang = (settings.get("languages") or ["en"])[0]
    lang = lang if lang in PHRASES else "en"
    return lang, PHRASES[lang]


def normalized(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    # Arabic vocalization marks and punctuation aren't transcription errors.
    text = "".join(c for c in text if not unicodedata.category(c).startswith("M"))
    return " ".join(re.findall(r"[^\W_]+", text))


def matches(text, expected):
    return bool(normalized(text)) and normalized(text) == normalized(expected)


def folder():
    root = paths.DATA / "runtime"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     suffix=".tmp", delete=False) as f:
        json.dump(value, f, ensure_ascii=False)
        name = Path(f.name)
    try:
        os.chmod(name, 0o600)
        name.replace(path)
    finally:
        name.unlink(missing_ok=True)


def read_json(path):
    try:
        value = json.loads(path.read_text("utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def state():
    data = read_json(folder() / "state.json")
    updated = data.get("updated", 0)
    if not isinstance(updated, (float, int)) or not 0 <= time.time() - updated < 4 or data.get("version") != APP_VERSION:
        return {"phase": "loading", "ready": False, "recording": False, "busy": False,
                "alive": False, "level": 0, "elapsed": 0}
    return {**data, "alive": True}


def publish(data):
    atomic_json(folder() / "state.json", {**data, "version": APP_VERSION, "updated": time.time()})


def valid_session(ident):
    if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{32}", ident):
        raise ValueError("Invalid practice session.")
    return ident


def result_path(ident):
    return folder() / ("practice-" + valid_session(ident) + ".json")


def result(ident):
    return read_json(result_path(ident))


def practice_result(ident, **data):
    atomic_json(result_path(ident), {"id": ident, "updated": time.time(), **data})


def lease(ident):
    atomic_json(folder() / ("lease-" + valid_session(ident) + ".json"), {"updated": time.time()})


def lease_alive(ident):
    data = read_json(folder() / ("lease-" + valid_session(ident) + ".json"))
    return time.time() - data.get("updated", 0) < 6


def clear_practice(ident):
    result_path(ident).unlink(missing_ok=True)
    (folder() / ("lease-" + valid_session(ident) + ".json")).unlink(missing_ok=True)


def send(action, **args):
    if action not in {"practice_start", "practice_stop", "practice_cancel", "record_start", "record_stop", "record_cancel", "quit", "update_check", "update_install"}:
        raise ValueError("Unsupported recording control.")
    queue = folder() / "commands"
    ident = f"{time.time_ns():020d}-{uuid.uuid4().hex}"
    atomic_json(queue / (ident + ".json"), {"action": action, "args": args, "created": time.time()})


def commands():
    queue = folder() / "commands"
    if not queue.exists():
        return []
    accepted = []
    for path in sorted(queue.glob("*.json"))[:32]:
        command = read_json(path)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue
        created = command.get("created", 0)
        if isinstance(created, (float, int)) and isinstance(command.get("args"), dict) and 0 <= time.time() - created < 10:
            accepted.append(command)
    return accepted
