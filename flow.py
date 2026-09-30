"""Flow: local dictation for Windows and Linux.

Hold Ctrl+Win and talk; release and the text is pasted where your cursor is. Press Space while
holding for hands-free, press again to finish. Esc cancels. The tray icon toggles hands-free on click.
"""
import ctypes
import json
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

import icons
import control
import health
from apps import resolve_app, display_name
import learn
import paths
import setup_tasks
import vault
import voicenotes
from engine import CATEGORY_NAMES, RATE, Engine, app_category, foreground_app
from hotkeys import Hotkeys, send_ctrl_v
from memory import Memory
from paths import DATA, HISTORY, MEMORY, SETTINGS, load_settings
from system import IS_WIN, dpi_aware, single_instance
from pill import Pill

user32 = ctypes.windll.user32 if IS_WIN else None
dpi_aware()

def light_taskbar():
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False


# ---------------------------------------------------------------- tray

def pin_tray_icon():
    """Once, on first run: show Flow's icon in the tray instead of the hidden ^ overflow. Users can unpin it."""
    if not IS_WIN:
        return
    import winreg
    marker = DATA / ".tray_pinned"
    if marker.exists():
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings") as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                sub = winreg.EnumKey(k, i)
                with winreg.OpenKey(k, sub, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as e:
                    try:
                        exe = winreg.QueryValueEx(e, "ExecutablePath")[0]
                    except OSError:
                        continue
                    if Path(exe).name.lower() == Path(sys.executable).name.lower() and Path(exe).parent == Path(sys.executable).parent:
                        winreg.SetValueEx(e, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        marker.write_text("1")
    except OSError:
        pass


def make_tray_class():
    import pystray
    if not IS_WIN:
        return pystray.Icon
    from pystray._util import win32

    class Tray(pystray.Icon):
        """pystray loads icons at the large-icon size and lets Windows shrink them (blurry); load at tray size."""

        def _assert_icon_handle(self):
            if self._icon_handle:
                return
            n = user32.GetSystemMetrics(49)  # SM_CXSMICON
            path = DATA / f".tray_{n}.ico"
            self.icon.resize((n, n), Image.LANCZOS).save(path, format="ICO", sizes=[(n, n)])
            self._icon_handle = win32.LoadImage(None, str(path), win32.IMAGE_ICON, n, n, win32.LR_LOADFROMFILE)

    return Tray


# ---------------------------------------------------------------- app

class Flow:
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.root = tk.Tk()
        self.root.withdraw()
        self.pill = Pill(self.root)
        self.settings = load_settings()
        self.memory = Memory(MEMORY, self.settings["languages"])
        self.migrate()
        self.mtimes = {}
        self.engine = Engine(self.memory)
        self.ready = False
        self.loading = True
        self.speech_signature = None
        self.recording = False
        self.mode = None              # "ptt" | "hands"
        self.busy = False
        self.chunks = []
        self.level = 0.0
        self.levels = deque([0.0] * 20, maxlen=20)
        self.events = queue.Queue()
        self.state = "idle"
        self.message = ""
        self.appear = 0.0
        self.t = 0.0
        self.hide_at = 0
        self.ui = None
        self.target_app = ("", "")
        self.practice = None
        self.compose_session = None
        self.record_started = 0
        self.state_started = time.time()
        self._last_status = 0
        self._last_error = ""
        self.icon_size = user32.GetSystemMetrics(49) if IS_WIN else 24
        self.light = light_taskbar()

        import pystray
        Tray = make_tray_class()
        self.tray = Tray("flow", self.tray_img("loading"), "Flow · getting ready", menu=pystray.Menu(
            pystray.MenuItem(lambda _: "Stop dictation" if self.recording else "Start dictation",
                             lambda: self.events.put("tray"), default=True),
            pystray.MenuItem("Open Flow", lambda: self.events.put("open")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Flow", lambda: self.events.put("quit")),
        ))
        try:
            if IS_WIN:
                self.tray.run_detached()
            else:
                threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception as ex:
            print("tray unavailable:", ex)

        if not IS_WIN:
            from system import install_launcher
            install_launcher(paths.launch_command())
        self.keys = Hotkeys(self.events.put, self.settings["shortcut"])
        threading.Thread(target=self.load_model, daemon=True).start()
        self.tick()

    def tray_img(self, state):
        return icons.tray(state, self.icon_size, self.light)

    def set_tray(self, state):
        self.tray.icon = self.tray_img(state)
        self.tray.update_menu()

    def reload(self):
        if self.recording or self.busy:
            return  # Finish this dictation with the engine and settings it started with.
        try:
            m = SETTINGS.stat().st_mtime
        except OSError:
            return
        if self.mtimes.get(SETTINGS) != m:
            self.mtimes[SETTINGS] = m
            self.settings = load_settings()
            self.keys.set_shortcut(self.settings["shortcut"])
            self.memory.set_languages(self.settings["languages"])
        if not self.loading and not self.busy and not self.recording and self.speech_signature != self._speech_signature(self.settings):
            self.loading = True
            self.ready = False
            self.set_tray("loading")
            threading.Thread(target=self.load_model, daemon=True).start()

    @staticmethod
    def _speech_signature(s):
        return tuple(s.get(k) for k in ("speech_provider", "model", "api_base", "api_model", "api_consent", "speech_revision"))

    def migrate(self):
        """Carry v2 dictionary words into memory; seed from Obsidian on first run."""
        for d in self.settings.pop("dictionary", []) or []:
            if d.get("word"):
                self.memory.add_term(d["word"], "you")
                if d.get("heard"):
                    self.memory.add_variant(d["heard"], d["word"])
        if self.settings.get("onboarded") and not self.memory.meta("vault_scanned"):
            threading.Thread(target=lambda: vault.scan(self.memory), daemon=True).start()

    def load_model(self):
        # a fresh install has no speech model yet: the window walks through setup, we wait for it
        asked = False
        from speech_api import configured
        while self.loading:
            s = load_settings()
            model = setup_tasks.find_model(s.get("model") or "large-v3") if s.get("speech_provider", "local") == "local" else None
            if s.get("onboarded") and (model or configured(s)):
                break
            if not asked:
                self.events.put("setup")
                asked = True
            time.sleep(1.5)
        if not self.loading:
            return
        self.settings = s
        self.memory.set_languages(s["languages"])
        health.save(health.baseline(s, "checking"))
        try:
            if s.get("speech_provider") == "api":
                self.engine.whisper = None
                self.engine.device = "api"
            else:
                self.engine.load(model)
        except Exception as error:
            health.failed_load(s, error)
            self.loading = False
            self._last_error = "Could not load the speech model. Choose another engine in Speech options."
            self.speech_signature = self._speech_signature(s)
            self.events.put(("error", "Could not load speech model. Open Settings and choose another model."))
            self.events.put("health_warning")
            return
        report = health.check(self.engine, s)
        health.save(report)
        gpu = setup_tasks.nvidia_gpu() if self.engine.device != "api" else None
        (DATA / "status.json").write_text(json.dumps({"device": self.engine.device, "gpu": gpu[0] if gpu else None,
                                                      "model": s.get("api_model") if self.engine.device == "api" else s.get("model") or "large-v3"}), "utf-8")
        self.speech_signature = self._speech_signature(s)
        self.loading = False
        self.events.put("ready")
        if report["status"] == "failed":
            self.events.put("health_warning")
        if self.settings.get("cleanup", True):
            self.engine.warm_llm()

    # ------------------------------------------------------------ recording

    def start(self, mode):
        import sounddevice as sd
        self.chunks, self.level = [], 0.0
        self.visual_level = 0
        self.levels.clear()
        self.target_app = foreground_app()
        # Each stream owns its gate and buffer. A late callback from an old
        # stream must not append audio to the next recording.
        accepting = self.capture_gate = threading.Event()
        accepting.set()
        chunks = self.chunks

        def cb(indata, frames, t, status):
            if accepting.is_set():
                chunks.append(indata[:, 0].copy())
                self.level = float(np.sqrt(np.mean(indata ** 2)))

        try:
            self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32", callback=cb)
            self.stream.start()
        except Exception:
            accepting.clear()
            if hasattr(self, "stream"):
                try:
                    self.stream.close()
                except Exception:
                    pass
            self.flash("Check your microphone")
            return
        self.recording = True
        self.record_started = time.time()
        self.keys.recording = True
        self.mode = mode
        self.set_state("listening")
        self.set_tray("recording")

    def _close_stream(self):
        gate = getattr(self, "capture_gate", None)
        if gate is not None:
            gate.clear()
        self.recording = False
        self.keys.recording = False
        self.level = self.visual_level = 0
        try:
            self.stream.stop()
        except Exception as error:
            print("microphone stop:", type(error).__name__)
        finally:
            try:
                self.stream.close()
            except Exception as error:
                print("microphone close:", type(error).__name__)
        self.set_tray("idle")

    def cancel(self):
        if self.recording:
            self._close_stream()
            self.set_state("idle")
        if self.practice:
            control.practice_result(self.practice["id"], phase="retry", matched=False,
                                    message="Recording cancelled. Try the phrase again.")
            self.practice = None

    def finish(self):
        self._close_stream()
        audio = np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)
        if len(audio) < RATE * 0.4 or np.sqrt(np.mean(audio ** 2)) < 0.002:
            if self.practice:
                control.practice_result(self.practice["id"], phase="retry", matched=False,
                                        message="No voice detected. Check your microphone and try again.")
                self.practice = None
            self.flash("Didn't catch that")
            return
        self.busy = True
        self.set_state("transcribing")
        if self.practice:
            context = dict(self.practice)
            control.practice_result(context["id"], phase="thinking", matched=False)
            threading.Thread(target=self.process_practice, args=(audio, context), daemon=True).start()
            return
        threading.Thread(target=self.process, args=(audio,), daemon=True).start()

    def process_practice(self, audio, context):
        """Use the selected real engine, without learning, history, notes or pasting."""
        try:
            settings = {**self.settings, "languages": [context["language"]]}
            text, _ = self.engine.transcribe(audio, settings)
            self.events.put(("practice_done", context["id"], text))
        except Exception as error:
            self.events.put(("practice_error", context["id"], "Could not transcribe. Check your speech engine and try again.", type(error).__name__))

    def process(self, audio):
        t0 = time.time()
        try:
            text, lang = self.engine.transcribe(audio, self.settings)
            if text:
                self.events.put(("stage", "polishing"))
                text = self.engine.cleanup(text, self.settings)
                self.memory.learn_dictation(text, lang)
                text = self.engine.finish(text, self.settings, self.target_app)
                self.category = app_category(self.target_app)
            self.events.put(("done", text, len(audio) / RATE, lang, round(time.time() - t0, 2)))
        except Exception as e:
            self.events.put(("error", type(e).__name__))

    def paste(self, text):
        from system import copy_text, read_clipboard
        try:
            old = read_clipboard()
        except Exception:
            old = None
        copy_text(text)
        time.sleep(0.04)
        pasted = send_ctrl_v()
        if pasted and old is not None:
            def restore():
                try:
                    if read_clipboard() == text:
                        copy_text(old)
                except Exception:
                    pass
            self.root.after(600, restore)
        elif not pasted:
            self.flash("Copied. Press Ctrl+V to paste")
        return pasted

    def save(self, text, seconds, lang, latency):
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), "text": text, "seconds": round(seconds, 2),
                 "words": len(text.split()), "lang": lang, "app": resolve_app(self.target_app),
                 "engine": self.engine.last_path, "latency": latency, "category": getattr(self, "category", "other")}
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:
            voicenotes.save(text, display_name(resolve_app(self.target_app)), self.settings)
        except Exception as e:
            print("voice notes:", e)

    # ------------------------------------------------------------ shortcut state machine

    def on_key(self, ev):
        if self.practice or (self.recording and self.mode == "compose"):
            if ev == "cancel":
                self.cancel()
            return
        if not self.ready or self.busy:
            return
        if ev == "down":
            if self.recording and self.mode == "hands":
                self.finish()
            elif not self.recording:
                self.start("ptt")
        elif ev == "up":
            if self.recording and self.mode == "ptt":
                self.finish()
        elif ev == "lock":
            if self.recording:
                self.mode = "hands"
        elif ev == "cancel":
            self.cancel()
        elif ev == "interrupt" and self.mode == "ptt":      # Ctrl+Win+Arrow etc. was a real shortcut
            self.cancel()

    def on_tray(self):
        if self.practice:
            return
        if not self.ready or self.busy:
            return
        if self.recording:
            self.finish()
        else:
            self.start("hands")

    # ------------------------------------------------------------ ui

    def set_state(self, state, message=""):
        if state != self.state:
            self.state_started = time.time()
        if state != "idle" and self.state == "idle":
            self.appear = 0.0
        self.state, self.message = state, message
        self.hide_at = 0

    def flash(self, message):
        self.set_state("message", message)
        self.hide_at = time.time() + 1.4

    def open_ui(self):
        if self.ui is not None and self.ui.poll() is None:
            if IS_WIN:
                from system import focus_process
                focus_process(self.ui.pid)
            return
        self.ui = subprocess.Popen(paths.launch_command("--window"))

    def tick(self):
        for command in control.commands():
            try:
                self.handle_control(command)
            except (ValueError, TypeError, KeyError):
                pass  # Reject malformed local commands without stopping the recorder.
        while not self.events.empty():
            ev = self.events.get()
            if ev in ("down", "up", "lock", "cancel", "interrupt"):
                self.on_key(ev)
            elif ev == "tray":
                self.on_tray()
            elif ev in ("open", "setup"):
                self.open_ui()
            elif ev == "health_warning":
                self.open_ui()
            elif ev == "quit":
                return self.quit()
            elif ev == "ready":
                self.ready = True
                self._last_error = ""
                self.root.after(3000, pin_tray_icon)
                self.set_tray("idle")
                self.tray.title = "Flow · hold " + self.settings["shortcut"].title().replace("+", " + ") + " to dictate"
            elif ev[0] == "stage":
                if self.busy:
                    self.set_state(ev[1])
            elif ev[0] in ("practice_done", "practice_error"):
                self.busy = False
                if self.practice and self.practice["id"] == ev[1]:
                    if ev[0] == "practice_done":
                        text = ev[2] or ""
                        matched = control.matches(text, self.practice["phrase"])
                        control.practice_result(ev[1], phase="passed" if matched else "retry", matched=matched,
                                                text=text[:500], message="You did it." if matched else "That was a little different. Say the phrase above and try again.")
                        self.flash("Nice. You did it." if matched else "Try that once more")
                    else:
                        health.failed_transcription(self.settings, ev[3] if len(ev)>3 else "SpeechError")
                        control.practice_result(ev[1], phase="retry", matched=False, message=ev[2])
                        self.flash("Check speech settings")
                    self.practice = None
                else:
                    self.set_state("idle")
            elif ev[0] == "done":
                self.busy = False
                _, text, seconds, lang, latency = ev
                if text:
                    pasted = False
                    if self.mode != "compose":
                        self.set_state("typing")
                        pasted = self.paste(text)
                    if self.settings.get("learn", True) and self.mode != "compose":
                        learn.watch(text, self.memory, lambda pairs: self.events.put(("learned", pairs)))
                    self.save(text, seconds, lang, latency)
                    if self.mode == "compose" or pasted:
                        self.flash("Saved to Recent" if self.mode == "compose" else "Typed")
                else:
                    self.flash("Didn't catch that")
            elif ev[0] == "learned":
                self.flash("Learned " + ", ".join(m for _, m in ev[1][:2]))
            elif ev[0] == "error":
                self.busy = False
                if self.ready:
                    health.failed_transcription(self.settings, ev[1])
                    self.open_ui()
                self.flash("Check speech settings")
                (DATA / "speech-error.json").write_text(json.dumps({"message": ev[1], "ts": time.time()}), "utf-8")
                print("error:", ev[1])

        now = time.time()
        if self.practice and self.recording:
            if not control.lease_alive(self.practice["id"]):
                self.cancel()
            elif now - self.record_started >= 15:
                self.finish()
        elif self.recording and self.mode == "compose" and not control.lease_alive(self.compose_session):
            self.cancel()
        if int(self.t * 30) % 30 == 0:
            self.reload()
        if self.hide_at and now > self.hide_at:
            self.set_state("idle")

        self.t += 1 / 60
        if self.recording:
            target = min(1.0, (self.level * 14) ** 0.8)
            self.visual_level = getattr(self, "visual_level", 0) + .2 * (target - getattr(self, "visual_level", 0))
            self.levels.append(self.visual_level)
        else:
            self.visual_level = 0
        if self.state != "idle":
            self.appear = min(1.0, self.appear + 0.25)
            locked = self.recording and self.mode == "hands"
            elapsed = now - (self.record_started if self.recording else self.state_started)
            self.pill.render(self.state, self.t, self.levels, self.message, self.appear, locked, elapsed)
            self.pill.show()
        else:
            self.pill.hide()
        if now - self._last_status > .2:
            self._last_status = now
            try:
                control.publish({"phase": self.state if self.ready else "error" if self._last_error else "loading", "ready": self.ready,
                                 "recording": self.recording, "busy": self.busy,
                                 "level": self.visual_level if self.recording else 0,
                                 "elapsed": round(max(0, now - (self.record_started if self.recording else self.state_started)), 1),
                                 "practice_id": self.practice["id"] if self.practice else None, "error": self._last_error})
            except OSError:
                pass  # A transient file lock must not stop the microphone/overlay loop.
        self.root.after(16, self.tick)

    def handle_control(self, command):
        action, args = command.get("action"), command.get("args") or {}
        if action == "quit":
            self.events.put("quit")
        elif action == "practice_start":
            ident = control.valid_session(args.get("id"))
            lang = args.get("language")
            if lang not in control.PHRASES or args.get("phrase") != control.PHRASES.get(lang) or not self.ready or self.busy or self.recording:
                control.practice_result(ident, phase="retry", matched=False, message="Flow isn't ready yet. Try again in a moment.")
                return
            self.practice = {"id": ident, "phrase": args["phrase"], "language": lang}
            self.start("practice")
            control.practice_result(ident, phase="recording" if self.recording else "retry", matched=False,
                                    message="" if self.recording else "Can't use the microphone. Check microphone access and try again.")
            if not self.recording:
                self.practice = None
        elif action in ("practice_stop", "practice_cancel"):
            if self.practice and args.get("id") == self.practice["id"]:
                if action == "practice_cancel":
                    self.cancel()
                elif self.recording:
                    self.finish()
            elif action == "practice_cancel" and not self.practice:
                control.clear_practice(control.valid_session(args.get("id")))
        elif action == "record_start":
            if self.ready and not self.busy and not self.recording and not self.practice:
                self.compose_session = control.valid_session(args.get("id"))
                self.start("compose")
        elif action == "record_stop":
            if self.recording and self.mode == "compose" and args.get("id") == self.compose_session:
                self.finish()
        elif action == "record_cancel":
            if self.recording and self.mode == "compose" and args.get("id") == self.compose_session:
                self.cancel()

    def quit(self):
        self.loading = False
        if self.recording:
            self.stream.stop()
        self.engine.unload_llm()
        if self.ui is not None and self.ui.poll() is None:
            self.ui.terminate()
        self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if not single_instance():
        return
    Flow().run()

if __name__ == "__main__":
    main()
