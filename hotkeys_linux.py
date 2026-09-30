"""Push-to-talk on Linux.

evdev reads the keyboard directly, so it works on X11 and Wayland alike; it needs read access to
/dev/input (be in the `input` group). Without that, pynput watches keys through X11 (and XWayland).
Unlike Windows, keys can't be swallowed here, so Space/Esc still reach the focused app.
"""
import os
import select
import threading

SHORTCUTS = {
    "ctrl+win": [{"lctrl", "rctrl"}, {"lmeta", "rmeta"}],
    "right ctrl": [{"rctrl"}],
    "caps lock": [{"caps"}],
    "f8": [{"f8"}],
}


class Hotkeys:
    def __init__(self, emit, shortcut="ctrl+win"):
        self.emit = emit
        self.groups = SHORTCUTS.get(shortcut, SHORTCUTS["ctrl+win"])
        self.held = set()
        self.active = False
        self.recording = False
        self.backend = None
        threading.Thread(target=self._run, daemon=True).start()

    def set_shortcut(self, shortcut):
        self.groups = SHORTCUTS.get(shortcut, SHORTCUTS["ctrl+win"])
        self.active = False

    # ------------------------------------------------------------ shared state machine (same as Windows)
    def handle(self, key, down):
        in_combo = any(key in g for g in self.groups)
        if down:
            if key in self.held and in_combo:
                return
            self.held.add(key)
        else:
            self.held.discard(key)
        if down and self.active and not in_combo and key not in ("space", "esc"):
            self.emit("interrupt")
            return
        now = all(self.held & g for g in self.groups)
        if now and not self.active:
            self.active = True
            self.emit("down")
        elif self.active and not now:
            self.active = False
            self.emit("up")
        if down and key == "space" and self.active:
            self.emit("lock")
        if down and key == "esc" and self.recording:
            self.emit("cancel")

    # ------------------------------------------------------------ backends
    def _run(self):
        if not self._evdev():
            self._pynput()

    def _evdev(self):
        try:
            import evdev
            from evdev import ecodes as e
        except ImportError:
            return False
        names = {e.KEY_LEFTCTRL: "lctrl", e.KEY_RIGHTCTRL: "rctrl", e.KEY_LEFTMETA: "lmeta", e.KEY_RIGHTMETA: "rmeta",
                 e.KEY_SPACE: "space", e.KEY_ESC: "esc", e.KEY_CAPSLOCK: "caps", e.KEY_F8: "f8"}
        devs = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
                keys = d.capabilities().get(e.EV_KEY, [])
                if e.KEY_A in keys and e.KEY_SPACE in keys and d.name != "flow-paste":
                    devs.append(d)
                else:
                    d.close()
            except (OSError, PermissionError):
                continue
        if not devs:
            return False
        self.backend = "evdev"
        fds = {d.fd: d for d in devs}
        while True:
            r, _, _ = select.select(fds, [], [])
            for fd in r:
                try:
                    for ev in fds[fd].read():
                        if ev.type == e.EV_KEY and ev.value in (0, 1):   # 2 = auto-repeat
                            self.handle(names.get(ev.code, f"k{ev.code}"), ev.value == 1)
                except OSError:
                    fds.pop(fd, None)
            if not fds:
                return True

    def _pynput(self):
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            print("hotkeys: native Wayland requires readable keyboard devices; see README Linux setup")
            return
        if not os.environ.get("DISPLAY"):
            print("hotkeys: no keyboard access (join the 'input' group) and no X11 display")
            return
        try:
            from pynput import keyboard as kb
        except Exception as ex:
            print("hotkeys: pynput unavailable:", ex)
            return
        K = kb.Key
        names = {K.ctrl_l: "lctrl", K.ctrl_r: "rctrl", K.ctrl: "lctrl", K.cmd: "lmeta", K.cmd_l: "lmeta",
                 K.cmd_r: "rmeta", K.space: "space", K.esc: "esc", K.caps_lock: "caps", K.f8: "f8"}
        with kb.Listener(on_press=lambda k: self.handle(names.get(k, str(k)), True),
                         on_release=lambda k: self.handle(names.get(k, str(k)), False)) as listener:
            listener.wait()
            self.backend = "x11"
            listener.join()
