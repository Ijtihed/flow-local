"""Flow window: onboarding, history, dictionary, snippets, settings. Started by the tray app with --window."""
import ctypes
import json
from collections import Counter
from pathlib import Path


from system import IS_WIN, startup_enabled, set_startup
import icons
from apps import canonical_app
from version import APP_VERSION
import paths
import setup_tasks
import vault
import voicenotes
import speech_api
import control
import health
from memory import Memory
from paths import HISTORY, MEMORY

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOT_APPS = {"explorer", "searchhost", "shellexperiencehost", "flow", "python", "pythonw"}


def read_history():
    if not HISTORY.exists():
        return []
    out = []
    for line in HISTORY.read_text("utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def write_history(items):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), "utf-8")


class Api:
    # ---- history
    def stamp(self):
        return HISTORY.stat().st_mtime if HISTORY.exists() else 0

    def history(self):
        return read_history()[::-1]

    def delete(self, ts):
        write_history([i for i in read_history() if i["ts"] != ts])

    def clear(self):
        write_history([])

    def copy(self, text):
        from system import copy_text
        copy_text(text)

    def edit(self, ts, text):
        """You fixed a dictation: save it and learn from the difference."""
        items, learned = read_history(), []
        for i in items:
            if i["ts"] == ts and i["text"] != text:
                learned = self._memory().learn_correction(i["text"], text)
                i["text"], i["words"] = text, len(text.split())
        write_history(items)
        return [f"{h} → {m}" for h, m in learned]

    # ---- settings
    def settings(self):
        s = paths.load_settings()
        s["version"] = APP_VERSION
        s["startup"] = self._startup()
        s["platform"] = "windows" if IS_WIN else "linux"
        s["session"] = __import__("os").environ.get("XDG_SESSION_TYPE", "x11")
        s["auto_learn"] = IS_WIN
        s["native_window"] = hasattr(self, "_window")
        try:
            s["api_key_saved"] = bool(speech_api.get_key())
        except Exception:
            s["api_key_saved"] = False
        s["speech_models"] = [{"id": k, "gb": v, "ready": bool(setup_tasks.find_model(k))}
                              for k, v in setup_tasks.MODEL_SIZE_GB.items()]
        s["ollama"] = setup_tasks.ollama_status()
        try:
            s["status"] = json.loads((paths.DATA / "status.json").read_text("utf-8"))
        except Exception:
            s["status"] = {}
        try:
            err = json.loads((paths.DATA / "speech-error.json").read_text("utf-8"))
            import time
            s["speech_error"] = err["message"] if time.time() - err["ts"] < 300 else ""
        except Exception:
            s["speech_error"] = ""
        gpu = setup_tasks.nvidia_gpu()
        s["gpu"] = gpu[0] if gpu else None
        s["cuda"] = setup_tasks.cuda_ready() if gpu else False
        return s

    def save_settings(self, patch):
        if any(k in patch for k in ("tutorial_seen", "tutorial_version")):
            raise ValueError("Complete the spoken practice to finish the tutorial.")
        if any(k in patch for k in ("speech_provider", "model", "api_base", "api_model", "api_consent", "api_key")):
            raise ValueError("Use the speech engine form to change models or API settings.")
        if "mood" in patch and patch["mood"] not in ("auto", "focused", "relaxed", "low-energy"):
            raise ValueError("Choose a supported mood.")
        if "startup" in patch:
            self._set_startup(bool(patch.pop("startup")))
        cur = paths.save_settings(patch)
        if "languages" in patch:
            self._memory().set_languages(cur["languages"])

    def configure_speech(self, config):
        provider = config.get("provider")
        if provider == "local":
            model = config.get("model", "large-v3")
            if model not in setup_tasks.MODEL_REPOS:
                raise ValueError("Choose a supported local speech model.")
            if paths.load_settings().get("onboarded") and not setup_tasks.find_model(model):
                raise ValueError("Download this speech model before switching to it.")
            paths.save_settings({"speech_provider": "local", "model": model, "api_consent": False,
                                 "speech_revision": __import__("time").time_ns()})
        elif provider == "api":
            if config.get("consent") is not True:
                raise ValueError("Accept the API data notice before enabling API speech.")
            base = speech_api.validated_base(config.get("base", ""))
            model = speech_api.validated_model(config.get("model", ""))
            key = config.get("key", "").strip()
            old = paths.load_settings()
            if not key and base != old.get("api_base"):
                raise ValueError("Enter the key for this provider when changing the API URL.")
            if not key and not speech_api.get_key():
                raise ValueError("Enter your speech API key.")
            if key:
                speech_api.save_key(key)
            paths.save_settings({"speech_provider": "api", "api_base": base, "api_model": model,
                                 "api_consent": True, "speech_revision": __import__("time").time_ns()})
        else:
            raise ValueError("Choose local or API speech.")
        return True

    def forget_api_key(self):
        (paths.DATA / "speech-key").unlink(missing_ok=True)
        paths.save_settings({"speech_provider": "local", "api_consent": False})
        return True

    def window_action(self, action):
        if not hasattr(self, "_window"):
            return False
        if action == "close":
            self._window.destroy()
        elif action == "minimize":
            self._window.minimize()
        elif action == "maximize":
            self._maximized = not getattr(self, "_maximized", False)
            self._window.maximize() if self._maximized else self._window.restore()
        return True

    def _startup(self):
        return startup_enabled()

    def _set_startup(self, on):
        set_startup(on, paths.launch_command())


    # ---- insights for Home
    def insights(self):
        from datetime import datetime
        items = read_history()
        words = sum(i.get("words", 0) for i in items)
        secs = sum(i.get("seconds", 0) for i in items)
        apps = Counter(canonical_app(i["app"]) for i in items if i.get("app") and i["app"].lower() not in NOT_APPS)
        today = datetime.now().date().isoformat()
        dates = {i.get("ts", "")[:10] for i in items if i.get("ts")}
        return {"words": words, "minutes_saved": round(max(0, words / 40 - secs / 60)),  # vs typing at 40 wpm
                "sessions": len(items), "today_count": sum(i.get("ts", "").startswith(today) for i in items),
                "active_days": len(dates), "last_used": items[-1].get("ts") if items else None,
                "wpm": round(words / (secs / 60)) if secs else 0, "apps": apps.most_common(5),
                "known": len([t for t in self._memory().terms() if t[1] in ("you", "learned", "history", "project")])}

    # ---- memory
    def _memory(self):
        if not hasattr(self, "_mem"):
            self._mem = Memory(MEMORY, paths.load_settings()["languages"])
        return self._mem

    def memory(self):
        return self._memory().listing()

    def add_term(self, word, heard=""):
        m = self._memory()
        m.add_term(word, "you")
        if heard:
            m.add_variant(heard, word, confirmed=True)

    def remove_term(self, word):
        self._memory().remove_term(word)

    def remove_fix(self, heard, term):
        self._memory().remove_variant(heard, term)

    def scan_vaults(self):
        return vault.scan(self._memory())

    # ---- voice notes
    def enable_voice_notes(self, on, folder=""):
        vn = paths.load_settings()["voice_notes"]
        if on:
            vaults = vault.vault_paths()
            if not folder:
                folder = str(voicenotes.default_folder(vaults[-1])) if vaults else str(paths.DATA / "Voice Notes")
            root = next((v for v in vaults if Path(folder).is_relative_to(v)), None)
            voicenotes.setup(Path(folder), root)
            vn = {"enabled": True, "folder": folder}
        else:
            vn = {**vn, "enabled": False}
        paths.save_settings({"voice_notes": vn})
        return vn

    # ---- first-run setup
    def diagnostics(self):
        return health.current()

    def copy_speech_report(self):
        from system import copy_text
        copy_text(json.dumps(health.current(), ensure_ascii=False, indent=2))
        return True

    def export_speech_report(self):
        import time
        report = health.current()
        folder = paths.DATA / "Reports"
        file = folder / ("Flow-speech-check-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
        control.atomic_json(file, report)
        return str(file)

    def _ensure_tray(self):
        if control.state().get("alive"):
            return
        import subprocess
        if not getattr(self, "_tray_launch", None) or self._tray_launch.poll() is not None:
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WIN else {"start_new_session": True}
            self._tray_launch = subprocess.Popen(paths.launch_command(), **options)

    def recording_status(self):
        if getattr(self, "_compose_id", None):
            control.lease(self._compose_id)
        return control.state()

    def record_start(self):
        self._ensure_tray()
        s = control.state()
        if not s.get("ready") or s.get("recording") or s.get("busy"):
            raise ValueError("Wait for Flow to be ready before recording.")
        self._compose_id = __import__("uuid").uuid4().hex
        control.lease(self._compose_id)
        control.send("record_start", id=self._compose_id)
        return True

    def record_stop(self):
        control.send("record_stop", id=getattr(self, "_compose_id", None))
        return True

    def record_cancel(self):
        control.send("record_cancel", id=getattr(self, "_compose_id", None))
        return True

    def practice_open(self):
        self._ensure_tray()
        import uuid
        if getattr(self, "_practice", None):
            control.send("practice_cancel", id=self._practice["id"])
        lang, phrase = control.phrase_for(paths.load_settings())
        self._practice = {"id": uuid.uuid4().hex, "language": lang, "phrase": phrase}
        control.lease(self._practice["id"])
        s = paths.load_settings()
        return {**self._practice, "api": s.get("speech_provider") == "api",
                "provider": __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(s.get("api_base", "")).hostname}

    def practice_start(self):
        if not getattr(self, "_practice", None):
            raise ValueError("Open the spoken practice first.")
        s = control.state()
        if not s.get("ready") or s.get("busy") or s.get("recording"):
            raise ValueError("Flow is still getting ready. Try again in a moment.")
        control.clear_practice(self._practice["id"])
        control.lease(self._practice["id"])
        control.practice_result(self._practice["id"], phase="starting", matched=False)
        control.send("practice_start", **self._practice)
        return True

    def practice_stop(self):
        if getattr(self, "_practice", None):
            control.practice_result(self._practice["id"], phase="thinking", matched=False)
            control.send("practice_stop", id=self._practice["id"])
        return True

    def practice_cancel(self):
        if getattr(self, "_practice", None):
            control.send("practice_cancel", id=self._practice["id"])
        return True

    def practice_status(self):
        if not getattr(self, "_practice", None):
            raise ValueError("Open the spoken practice first.")
        ident = self._practice["id"]
        if __import__("time").time() - getattr(self, "_lease_time", 0) > 1:
            control.lease(ident)
            self._lease_time = __import__("time").time()
        runtime = control.state()
        result = control.result(ident)
        return {**runtime, **result, "phrase": self._practice["phrase"],
                "message": result.get("message") or runtime.get("error", ""),
                "phase": result.get("phase", "error" if runtime.get("error") and not runtime.get("ready") else "ready" if runtime.get("ready") and not runtime.get("busy") and not runtime.get("recording") else "loading")}

    def practice_complete(self):
        if not getattr(self, "_practice", None):
            raise ValueError("Complete the spoken practice first.")
        result = control.result(self._practice["id"])
        if result.get("matched") is not True or not control.matches(result.get("text", ""), self._practice["phrase"]):
            raise ValueError("Say the practice phrase before continuing.")
        paths.save_settings({"tutorial_seen": True, "tutorial_version": control.TUTORIAL_VERSION})
        control.clear_practice(self._practice["id"])
        self._practice = None
        return True

    def system(self):
        return setup_tasks.system_info()

    def setup_run(self, task, arg=None):
        return setup_tasks.run(task, *([arg] if arg else []))

    def setup_status(self):
        return dict(setup_tasks.state)

    def finish_onboarding(self, name, languages, scan):
        m = self._memory()
        m.set_languages(languages)
        if name:
            m.add_term(name, "you")
            for part in name.split():
                if m.is_rare(part):
                    m.add_term(part, "you")
        if scan:
            vault.scan(m)
        else:
            import techvocab
            techvocab.seed(m)
        paths.save_settings({"name": name, "languages": languages, "onboarded": True})
        return True


def style_window(window):
    """Light title bar with Flow's own icon instead of Python's."""
    try:
        hwnd = window.native.Handle.ToInt32()
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(0)), 4)          # light mode
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(0xF5F7F7)), 4)   # caption = sidebar
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(ctypes.c_int(0xE7EAEA)), 4)   # border = hairline
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        for which, metric in ((0, 49), (1, 11)):  # ICON_SMALL/SM_CXSMICON, ICON_BIG/SM_CXICON
            n = user32.GetSystemMetrics(metric)
            h = user32.LoadImageW(None, str(paths.ICON), 1, n, n, 0x10)
            user32.SendMessageW(hwnd, 0x80, which, h)  # WM_SETICON
    except Exception as e:
        print("style_window:", e)


def main():
    if not IS_WIN:
        from ui_linux import serve
        serve(Api())
        return
    import webview
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Flow.Dictation")
    if not paths.FROZEN:
        icons.ensure_app_ico(paths.ICON)
    api = Api()
    win = webview.create_window("Flow", str(paths.APP / "ui.html"), js_api=api, width=1040, height=740,
                                min_size=(720, 520), background_color="#FFFFFF", frameless=True,
                                easy_drag=False)
    api._window = win
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    win.events.shown += lambda: style_window(win)
    webview.start()


if __name__ == "__main__":
    main()
