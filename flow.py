"""Flow: Wispr-style dictation for Windows.

Hold Ctrl+Win and talk; release and the text is pasted where your cursor is. Double-tap (or press Space while
holding) for hands-free, press again to finish. Esc cancels. The tray icon toggles hands-free on click.
"""
import ctypes
import ctypes.wintypes as wt
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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import icons
import learn
import paths
import setup_tasks
import vault
import voicenotes
from engine import CATEGORY_NAMES, RATE, Engine, app_category, foreground_app
from hotkeys import Hotkeys, send_ctrl_v
from memory import Memory
from paths import DATA, HISTORY, MEMORY, SETTINGS, load_settings

TAP = 0.3          # a press shorter than this is a tap, not push-to-talk
DOUBLE_TAP = 0.45  # second press within this after a tap -> hands-free

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def light_taskbar():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False


# ---------------------------------------------------------------- overlay pill

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("op", ctypes.c_byte), ("flags", ctypes.c_byte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


user32.GetParent.restype = wt.HWND
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
                                       ctypes.POINTER(wt.POINT), wt.DWORD, ctypes.POINTER(BLENDFUNCTION), wt.DWORD]


class Pill:
    """Anti-aliased, per-pixel-alpha, click-through overlay (Win32 layered window fed with PIL frames)."""

    SS = 3  # supersampling

    def __init__(self, root):
        self.s = user32.GetDpiForSystem() / 96
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry("1x1+0+0")
        self.win.update_idletasks()
        self.hwnd = user32.GetParent(self.win.winfo_id())
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        # layered | click-through | topmost | no taskbar button | never takes focus
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style | 0x80000 | 0x20 | 0x8 | 0x80 | 0x08000000)
        self.win.withdraw()
        self.visible = False
        self.font = self._font(12.5)
        self.shadows = {}

    def _font(self, size):
        for name in ("SegUIVar.ttf", "segoeui.ttf", "Inter_FXH-Regular.ttf"):
            try:
                return ImageFont.truetype(name, int(size * self.s * self.SS))
            except OSError:
                continue
        return ImageFont.load_default()

    def show(self):
        if not self.visible:
            self.win.deiconify()
            self.visible = True

    def hide(self):
        if self.visible:
            self.win.withdraw()
            self.visible = False

    def _shadow(self, w, h, m, r):
        key = (w, h)
        if key not in self.shadows:
            img = Image.new("L", (w + 2 * m, h + 2 * m), 0)
            ImageDraw.Draw(img).rounded_rectangle((m, m + m * 0.35, m + w, m + h + m * 0.35), r, fill=70)
            self.shadows[key] = img.filter(ImageFilter.GaussianBlur(m / 2.4))
        return self.shadows[key]

    def render(self, state, t, levels, message, appear, locked=False):
        k = self.s * self.SS
        text_w = 0
        if state == "message":
            text_w = self.font.getlength(message) / k
        w_l = 128 if state != "message" else max(128, text_w + 40)
        if locked:
            w_l = 150  # room for the hands-free dot
        h_l = 38
        # Apple-ish entrance: grow from a narrow capsule
        e = 1 - (1 - appear) ** 3
        w_l = h_l + (w_l - h_l) * e
        W, H, M, R = int(w_l * k), int(h_l * k), int(18 * k), int(h_l * k / 2)
        img = Image.new("RGBA", (W + 2 * M, H + 2 * M), (0, 0, 0, 0))
        img.putalpha(self._shadow(W, H, M, R))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((M, M, M + W, M + H), R, fill=(255, 255, 255, 252), outline=(0, 0, 0, 26),
                            width=max(1, int(k)))
        cx, cy = M + W / 2, M + H / 2
        if e > 0.6:
            a = int(255 * min(1, (e - 0.6) / 0.4))
            if state == "listening":
                n, gap, bw = 13, 6.2 * k, 2.6 * k
                if locked:  # hands-free: pulsing red dot on the left, bars nudged right
                    r = 3.6 * k * (0.85 + 0.15 * np.sin(t * 5))
                    dx = M + 19 * k
                    d.ellipse((dx - r, cy - r, dx + r, cy + r), fill=(255, 69, 88, a))
                    cx += 9 * k
                x0 = cx - (n - 1) * gap / 2
                for i in range(n):
                    lv = levels[-n + i] if len(levels) >= n else 0.0
                    env = 1 - abs(i - (n - 1) / 2) / ((n - 1) / 2) * 0.45
                    bh = (3 + 19 * min(1.0, lv) * env) * k
                    x = x0 + i * gap
                    d.rounded_rectangle((x - bw / 2, cy - bh / 2, x + bw / 2, cy + bh / 2), bw / 2,
                                        fill=(22, 22, 24, a))
            elif state == "transcribing":
                n, gap, bw = 13, 6.2 * k, 2.6 * k
                x0 = cx - (n - 1) * gap / 2
                for i in range(n):
                    wave = 0.5 + 0.5 * np.sin(t * 7 - i * 0.55)
                    bh = (3 + 5 * wave) * k
                    x = x0 + i * gap
                    d.rounded_rectangle((x - bw / 2, cy - bh / 2, x + bw / 2, cy + bh / 2), bw / 2,
                                        fill=(22, 22, 24, int(a * (0.3 + 0.7 * wave))))
            else:
                d.text((cx, cy), message, font=self.font, fill=(29, 29, 31, a), anchor="mm")
        img = img.resize((img.width // self.SS, img.height // self.SS), Image.LANCZOS)
        self._blit(img)

    def _blit(self, img):
        w, h = img.size
        arr = np.asarray(img, dtype=np.uint16)
        alpha = arr[..., 3:4]
        bgra = np.empty((h, w, 4), np.uint8)
        bgra[..., :3] = (arr[..., [2, 1, 0]] * alpha // 255).astype(np.uint8)
        bgra[..., 3] = arr[..., 3]
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x, y = (sw - w) // 2, sh - h - int(64 * self.s)

        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bmp = gdi32.CreateDIBSection(mem, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, bgra.tobytes(), w * h * 4)
        old = gdi32.SelectObject(mem, bmp)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wt.POINT(x, y)), ctypes.byref(wt.SIZE(w, h)),
                                   mem, ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(blend), 2)
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


# ---------------------------------------------------------------- tray

def pin_tray_icon():
    """Once, on first run: show Flow's icon in the tray instead of the hidden ^ overflow. Users can unpin it."""
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
        self.recording = False
        self.mode = None              # "ptt" | "hands"
        self.pressed_at = 0
        self.tap_pending = 0          # time a quick tap ended, waiting to see if it's a double-tap
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
        self.icon_size = user32.GetSystemMetrics(49)
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
        self.tray.run_detached()

        self.keys = Hotkeys(self.events.put, self.settings["shortcut"])
        threading.Thread(target=self.load_model, daemon=True).start()
        self.tick()

    def tray_img(self, state):
        return icons.tray(state, self.icon_size, self.light)

    def set_tray(self, state):
        self.tray.icon = self.tray_img(state)
        self.tray.update_menu()

    def reload(self):
        try:
            m = SETTINGS.stat().st_mtime
        except OSError:
            return
        if self.mtimes.get(SETTINGS) != m:
            self.mtimes[SETTINGS] = m
            self.settings = load_settings()
            self.keys.set_shortcut(self.settings["shortcut"])
            self.memory.set_languages(self.settings["languages"])

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
        while True:
            s = load_settings()
            model = setup_tasks.find_model(s.get("model") or "large-v3")
            if s.get("onboarded") and model:
                break
            if not asked:
                self.events.put("setup")
                asked = True
            time.sleep(1.5)
        self.settings = s
        self.memory.set_languages(s["languages"])
        self.engine.load(model)
        gpu = setup_tasks.nvidia_gpu()
        (DATA / "status.json").write_text(json.dumps({"device": self.engine.device, "gpu": gpu[0] if gpu else None,
                                                      "model": s.get("model") or "large-v3"}), "utf-8")
        self.events.put("ready")
        if self.settings.get("cleanup", True):
            self.engine.warm_llm()

    # ------------------------------------------------------------ recording

    def start(self, mode):
        import sounddevice as sd
        self.chunks, self.level = [], 0.0
        self.target_app = foreground_app()

        def cb(indata, frames, t, status):
            self.chunks.append(indata[:, 0].copy())
            self.level = float(np.sqrt(np.mean(indata ** 2)))

        self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32", callback=cb)
        self.stream.start()
        self.recording = True
        self.keys.recording = True
        self.mode = mode
        self.set_state("listening")
        self.set_tray("recording")

    def _close_stream(self):
        self.stream.stop()
        self.stream.close()
        self.recording = False
        self.keys.recording = False
        self.tap_pending = 0
        self.set_tray("idle")

    def cancel(self):
        if self.recording:
            self._close_stream()
            self.set_state("idle")

    def finish(self):
        self._close_stream()
        audio = np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)
        if len(audio) < RATE * 0.4 or np.sqrt(np.mean(audio ** 2)) < 0.002:
            self.flash("Didn't catch that")
            return
        self.busy = True
        self.set_state("transcribing")
        threading.Thread(target=self.process, args=(audio,), daemon=True).start()

    def process(self, audio):
        t0 = time.time()
        try:
            text, lang = self.engine.transcribe(audio, self.settings)
            if text:
                text = self.engine.cleanup(text, self.settings)
                self.memory.learn_dictation(text, lang)
                text = self.engine.finish(text, self.settings, self.target_app)
                self.category = app_category(self.target_app)
            self.events.put(("done", text, len(audio) / RATE, lang, round(time.time() - t0, 2)))
        except Exception as e:
            self.events.put(("error", repr(e)))

    def paste(self, text):
        import pyperclip
        try:
            old = pyperclip.paste()
        except Exception:
            old = None
        pyperclip.copy(text)
        time.sleep(0.04)
        send_ctrl_v()
        if old is not None:
            self.root.after(600, lambda: pyperclip.copy(old))

    def save(self, text, seconds, lang, latency):
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), "text": text, "seconds": round(seconds, 2),
                 "words": len(text.split()), "lang": lang, "app": self.target_app[0],
                 "engine": self.engine.last_path, "latency": latency, "category": getattr(self, "category", "other")}
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:
            voicenotes.save(text, self.target_app[0].title() if self.target_app[0] else "", self.settings)
        except Exception as e:
            print("voice notes:", e)

    # ------------------------------------------------------------ shortcut state machine

    def on_key(self, ev):
        now = time.time()
        if not self.ready or self.busy:
            return
        if ev == "down":
            if self.recording and self.mode == "hands":
                self.finish()
            elif self.recording and self.tap_pending:       # second tap -> hands-free
                self.tap_pending = 0
                self.mode = "hands"
            elif not self.recording:
                self.pressed_at = now
                self.start("ptt")
        elif ev == "up":
            if self.recording and self.mode == "ptt":
                if now - self.pressed_at < TAP:
                    self.tap_pending = now                  # maybe a double-tap; decided in tick()
                else:
                    self.finish()
        elif ev == "lock":
            if self.recording:
                self.mode = "hands"
        elif ev == "cancel":
            self.cancel()
        elif ev == "interrupt" and self.mode == "ptt":      # Ctrl+Win+Arrow etc. was a real shortcut
            self.cancel()

    def on_tray(self):
        if not self.ready or self.busy:
            return
        if self.recording:
            self.finish()
        else:
            self.start("hands")

    # ------------------------------------------------------------ ui

    def set_state(self, state, message=""):
        if state != "idle" and self.state == "idle":
            self.appear = 0.0
        self.state, self.message = state, message
        self.hide_at = 0

    def flash(self, message):
        self.set_state("message", message)
        self.hide_at = time.time() + 1.4

    def open_ui(self):
        if self.ui is not None and self.ui.poll() is None:
            hwnd = user32.FindWindowW(None, "Flow")
            if hwnd:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
            return
        self.ui = subprocess.Popen(paths.launch_command("--window"))

    def tick(self):
        while not self.events.empty():
            ev = self.events.get()
            if ev in ("down", "up", "lock", "cancel", "interrupt"):
                self.on_key(ev)
            elif ev == "tray":
                self.on_tray()
            elif ev in ("open", "setup"):
                self.open_ui()
            elif ev == "quit":
                return self.quit()
            elif ev == "ready":
                self.ready = True
                self.root.after(3000, pin_tray_icon)
                self.set_tray("idle")
                self.tray.title = "Flow · hold " + self.settings["shortcut"].title().replace("+", " + ") + " to dictate"
            elif ev[0] == "done":
                self.busy = False
                _, text, seconds, lang, latency = ev
                if text:
                    self.set_state("idle")
                    self.paste(text)
                    if self.settings.get("learn", True):
                        learn.watch(text, self.memory, lambda pairs: self.events.put(("learned", pairs)))
                    self.save(text, seconds, lang, latency)
                else:
                    self.flash("Didn't catch that")
            elif ev[0] == "learned":
                self.flash("Learned " + ", ".join(m for _, m in ev[1][:2]))
            elif ev[0] == "error":
                self.busy = False
                self.flash("Something went wrong")
                print("error:", ev[1])

        now = time.time()
        if self.tap_pending and now - self.tap_pending > DOUBLE_TAP:
            self.cancel()                                   # a lone quick tap: nothing to dictate
        if int(self.t * 30) % 30 == 0:
            self.reload()
        if self.hide_at and now > self.hide_at:
            self.set_state("idle")

        self.t += 1 / 30
        if self.recording:
            self.levels.append(min(1.0, (self.level * 14) ** 0.8))
        if self.state != "idle":
            self.appear = min(1.0, self.appear + 0.12)
            locked = self.recording and self.mode == "hands"
            self.pill.render(self.state, self.t, self.levels, self.message, self.appear, locked)
            self.pill.show()
        else:
            self.pill.hide()
        self.root.after(33, self.tick)

    def quit(self):
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
    ctypes.windll.kernel32.CreateMutexW(None, False, "FlowDictationMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:
        sys.exit(0)
    Flow().run()


if __name__ == "__main__":
    main()
