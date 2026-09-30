"""Low-level keyboard hook for push-to-talk, the way Wispr does it on Windows.

Hold the shortcut to talk, release to paste. While holding, Space locks hands-free.
Double-tap the shortcut for hands-free too. Esc cancels. The hook swallows the keys it
uses (Space, Esc, Caps Lock, F8) so they never reach the app you're typing in.
"""
import ctypes
import ctypes.wintypes as wt
import threading

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
LLKHF_INJECTED = 0x10
VK = {"lctrl": 0xA2, "rctrl": 0xA3, "lwin": 0x5B, "rwin": 0x5C, "space": 0x20, "esc": 0x1B,
      "caps": 0x14, "f8": 0x77, "ctrl": 0x11}
MASK_KEY = 0xE8  # unassigned VK; tapping it while Win is down stops the Start menu opening (AutoHotkey's trick)

# shortcut name -> list of key groups; every group needs one key held
SHORTCUTS = {
    "ctrl+win": [{VK["lctrl"], VK["rctrl"]}, {VK["lwin"], VK["rwin"]}],
    "right ctrl": [{VK["rctrl"]}],
    "caps lock": [{VK["caps"]}],
    "f8": [{VK["f8"]}],
}
SWALLOW = {VK["caps"], VK["f8"]}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
kernel32.GetModuleHandleW.restype = wt.HMODULE


def tap(vk):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)


class Hotkeys:
    def __init__(self, emit, shortcut="ctrl+win"):
        self.emit = emit                   # emit("down" | "up" | "lock" | "cancel")
        self.groups = SHORTCUTS.get(shortcut, SHORTCUTS["ctrl+win"])
        self.held = set()
        self.active = False
        self.recording = False             # set by the app so Esc is only swallowed while it matters
        self._proc = HOOKPROC(self._hook)
        threading.Thread(target=self._run, daemon=True).start()

    def set_shortcut(self, shortcut):
        self.groups = SHORTCUTS.get(shortcut, SHORTCUTS["ctrl+win"])
        self.active = False

    def _run(self):
        self.hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _hook(self, n, wparam, lparam):
        if n == 0:
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not kb.flags & LLKHF_INJECTED and self._handle(kb.vkCode, wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                return 1
        return user32.CallNextHookEx(None, n, wparam, lparam)

    def _handle(self, vk, down):
        in_combo = any(vk in g for g in self.groups)
        if down:
            if vk in self.held and in_combo:      # auto-repeat
                return vk in SWALLOW
            # drop keys whose key-up we never saw (e.g. Win+L locked the screen mid-press)
            self.held = {k for k in self.held if user32.GetAsyncKeyState(k) & 0x8000}
            self.held.add(vk)
        else:
            self.held.discard(vk)

        if down and self.active and not in_combo and vk not in (VK["space"], VK["esc"]):
            self.emit("interrupt")                # Ctrl+Win+Arrow etc.: a real shortcut, not dictation
            return False

        now_active = all(self.held & g for g in self.groups)
        if now_active and not self.active:
            self.active = True
            if vk in (VK["lwin"], VK["rwin"]) or self.held & {VK["lwin"], VK["rwin"]}:
                tap(MASK_KEY)
            self.emit("down")
        elif self.active and not now_active:
            self.active = False
            self.emit("up")

        if down and vk == VK["space"] and self.active:
            self.emit("lock")
            return True
        if down and vk == VK["esc"] and self.recording:
            self.emit("cancel")
            return True
        return in_combo and vk in SWALLOW
