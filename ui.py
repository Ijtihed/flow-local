"""Flow window: onboarding, history, dictionary, snippets, settings. Started by the tray app with --window."""
import ctypes
import json
from collections import Counter
from pathlib import Path


from system import IS_WIN, startup_enabled, set_startup
import icons
import paths
import setup_tasks
import vault
import voicenotes
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
        s["startup"] = self._startup()
        s["platform"] = "windows" if IS_WIN else "linux"
        s["session"] = __import__("os").environ.get("XDG_SESSION_TYPE", "x11")
        s["auto_learn"] = IS_WIN
        s["ollama"] = setup_tasks.ollama_status()
        try:
            s["status"] = json.loads((paths.DATA / "status.json").read_text("utf-8"))
        except Exception:
            s["status"] = {}
        gpu = setup_tasks.nvidia_gpu()
        s["gpu"] = gpu[0] if gpu else None
        s["cuda"] = setup_tasks.cuda_ready() if gpu else False
        return s

    def save_settings(self, patch):
        if "startup" in patch:
            self._set_startup(bool(patch.pop("startup")))
        cur = paths.save_settings(patch)
        if "languages" in patch:
            self._memory().set_languages(cur["languages"])

    def _startup(self):
        return startup_enabled()

    def _set_startup(self, on):
        set_startup(on, paths.launch_command())


    # ---- insights for Home
    def insights(self):
        items = read_history()
        words = sum(i.get("words", 0) for i in items)
        secs = sum(i.get("seconds", 0) for i in items)
        apps = Counter(i["app"] for i in items if i.get("app") and i["app"].lower() not in NOT_APPS)
        return {"words": words, "minutes_saved": round(max(0, words / 40 - secs / 60)),  # vs typing at 40 wpm
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
    win = webview.create_window("Dictation settings", str(paths.APP / "ui.html"), js_api=Api(), width=1000, height=700,
                                min_size=(720, 520), background_color="#FFFFFF")
    win.events.shown += lambda: style_window(win)
    webview.start()


if __name__ == "__main__":
    main()
