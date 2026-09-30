"""Everything that differs between Windows and Linux, behind one small interface."""
import ctypes
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")


def dpi_aware():
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


_lock = None
_dll_handles = []


def single_instance(name="FlowDictation"):
    """True if we're the only running Flow."""
    global _lock
    if IS_WIN:
        ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
        _lock = ctypes.windll.kernel32.CreateMutexW(None, False, name + "Mutex")
        return ctypes.windll.kernel32.GetLastError() != 183
    import fcntl
    import paths
    paths.DATA.mkdir(parents=True, exist_ok=True)
    _lock = open(paths.DATA / ".lock", "w")
    try:
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


# ------------------------------------------------------------ active app

def foreground_app():
    """(program name, window title) of the window the text will land in."""
    if IS_WIN:
        return _foreground_win()
    try:
        return _foreground_x11()
    except Exception:
        return "", ""     # Wayland does not expose the focused app to other programs


def _foreground_win():
    import ctypes.wintypes as wt
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wt.HWND
    kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel32.OpenProcess.restype = wt.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    hwnd = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, 512)
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if h:
        buf = ctypes.create_unicode_buffer(520)
        size = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            exe = Path(buf.value).stem.lower()
        kernel32.CloseHandle(h)
    return exe, title.value


_xdisplay = None


def _foreground_x11():
    global _xdisplay
    from Xlib import X, display
    if _xdisplay is None:
        _xdisplay = display.Display()
    d = _xdisplay
    root = d.screen().root
    active = root.get_full_property(d.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
    if not active or not active.value[0]:
        return "", ""
    w = d.create_resource_object("window", active.value[0])
    cls = w.get_wm_class() or ("", "")
    name = w.get_full_property(d.intern_atom("_NET_WM_NAME"), 0)
    title = name.value.decode("utf-8", "ignore") if name and isinstance(name.value, bytes) else (w.get_wm_name() or "")
    exe = (cls[1] or cls[0] or "").lower()
    return {"google-chrome": "chrome", "microsoft-edge": "msedge", "code-oss": "code"}.get(exe, exe), title


# ------------------------------------------------------------ paste

def paste():
    """Press Ctrl+V in whatever window has focus."""
    if IS_WIN:
        user32 = ctypes.windll.user32
        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(0x56, 0, 0, 0)
        user32.keybd_event(0x56, 0, 2, 0)
        user32.keybd_event(0x11, 0, 2, 0)
        return True
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    try:                                   # uinput works on X11 and Wayland when /dev/uinput is writable
        from evdev import UInput, ecodes as e
        with UInput({e.EV_KEY: [e.KEY_LEFTCTRL, e.KEY_V]}, name="flow-paste") as ui:
            import time
            time.sleep(0.05)
            for code, val in ((e.KEY_LEFTCTRL, 1), (e.KEY_V, 1), (e.KEY_V, 0), (e.KEY_LEFTCTRL, 0)):
                ui.write(e.EV_KEY, code, val)
                ui.syn()
        return True
    except Exception:
        pass
    for cmd in ((["wtype", "-M", "ctrl", "v", "-m", "ctrl"],) if wayland else (["xdotool", "key", "--clearmodifiers", "ctrl+v"],)):
        if shutil.which(cmd[0]):
            if subprocess.run(cmd, timeout=3).returncode == 0:
                return True
    if wayland:
        return False
    try:
        from pynput.keyboard import Controller, Key
        k = Controller()
        with k.pressed(Key.ctrl):
            k.press("v")
            k.release("v")
        return True
    except Exception as ex:
        print("paste: no way to send Ctrl+V:", ex)
        return False


def copy_text(text):
    if not IS_WIN and os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        subprocess.run(["wl-copy", "--type", "text/plain;charset=utf-8"], input=text.encode(), check=True, timeout=3)
    else:
        import pyperclip
        if IS_LINUX and os.environ.get("DISPLAY") and shutil.which("xclip"):
            pyperclip.set_clipboard("xclip")
        pyperclip.copy(text)


def read_clipboard():
    if not IS_WIN and os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        return subprocess.check_output(["wl-paste", "--no-newline"], timeout=3).decode()
    import pyperclip
    if IS_LINUX and os.environ.get("DISPLAY") and shutil.which("xclip"):
        pyperclip.set_clipboard("xclip")
    return pyperclip.paste()


def focus_process(pid):
    """Activate the settings window that belongs to our child process."""
    if not IS_WIN:
        return
    import ctypes.wintypes as wt
    u = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def visit(hwnd, _):
        owner = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd):
            u.ShowWindow(hwnd, 9)
            u.SetForegroundWindow(hwnd)
            return False
        return True
    callback = callback_type(visit)
    u.EnumWindows(callback, 0)


# ------------------------------------------------------------ start at login

def _autostart_file():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "flow.desktop"


def startup_enabled():
    if IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, "Flow")
                return True
        except OSError:
            return False
    return _autostart_file().exists()


def set_startup(on, command):
    if IS_WIN:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "Flow", 0, winreg.REG_SZ, " ".join(f'"{c}"' for c in command))
            else:
                try:
                    winreg.DeleteValue(k, "Flow")
                except OSError:
                    pass
        return
    f = _autostart_file()
    if on:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(desktop_entry(command), "utf-8")
    else:
        f.unlink(missing_ok=True)


def desktop_entry(command, name="Flow", comment="Hold Ctrl+Super, talk, let go"):
    import paths
    def quote(c):
        return '"' + str(c).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
    exe = " ".join(quote(c) for c in command)
    return (f"[Desktop Entry]\nType=Application\nName={name}\nComment={comment}\nExec={exe}\n"
            f"Icon={paths.DATA / 'icon.png'}\nTerminal=false\nCategories=Utility;Accessibility;\n")


def install_launcher(command):
    """Linux: add Flow and Flow Settings to the app menu (once)."""
    if not IS_LINUX:
        return
    import icons
    import paths
    apps = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    icons.app_icon(256).save(paths.DATA / "icon.png")
    (apps / "flow.desktop").write_text(desktop_entry(command), "utf-8")
    (apps / "flow-settings.desktop").write_text(desktop_entry(command + ["--window"], "Flow Settings", "History, dictionary and settings"), "utf-8")


# ------------------------------------------------------------ misc

def obsidian_config():
    if IS_WIN:
        return [Path(os.environ.get("APPDATA", "")) / "obsidian" / "obsidian.json"]
    home = Path.home()
    return [Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "obsidian" / "obsidian.json",
            home / ".var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json",
            home / "snap/obsidian/current/.config/obsidian/obsidian.json"]


def display_name():
    if IS_WIN:
        try:
            buf = ctypes.create_unicode_buffer(256)
            size = ctypes.c_ulong(256)
            if ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(size)) and buf.value.strip():
                return buf.value.strip()
        except Exception:
            pass
    else:
        try:
            import pwd
            gecos = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
            if gecos:
                return gecos
        except Exception:
            pass
    import getpass
    return getpass.getuser().replace(".", " ").title()


def open_url(url):
    import webbrowser
    webbrowser.open(url)


# ------------------------------------------------------------ NVIDIA

def _libcuda():
    try:
        return ctypes.WinDLL("nvcuda.dll") if IS_WIN else ctypes.CDLL("libcuda.so.1")
    except OSError:
        return None


def nvidia_gpu():
    """(name, vram_gb) of the first NVIDIA GPU, straight from the driver, or None."""
    cu = _libcuda()
    if not cu or cu.cuInit(0) != 0:
        return None
    n = ctypes.c_int()
    if cu.cuDeviceGetCount(ctypes.byref(n)) != 0 or n.value < 1:
        return None
    dev = ctypes.c_int()
    cu.cuDeviceGet(ctypes.byref(dev), 0)
    name = ctypes.create_string_buffer(128)
    cu.cuDeviceGetName(name, 128, dev)
    mem = ctypes.c_size_t()
    fn = getattr(cu, "cuDeviceTotalMem_v2", None) or cu.cuDeviceTotalMem
    fn(ctypes.byref(mem), dev)
    return name.value.decode(errors="ignore"), round(mem.value / 2**30, 1)


def cuda_dirs():
    import paths
    dirs = [str(paths.CUDA)] if paths.CUDA.exists() else []
    sub = "bin" if IS_WIN else "lib"
    for sp in map(Path, sys.path):
        dirs += glob.glob(str(sp / "nvidia" / "*" / sub))
    return dirs


def cuda_ready():
    names = {f.name.lower() for d in cuda_dirs() for f in Path(d).iterdir() if f.is_file()}
    if IS_WIN:
        return "cublas64_12.dll" in names and any(n.startswith("cudnn64_9") for n in names)
    return any(n.startswith("libcublas.so.12") for n in names) and any(n.startswith("libcudnn.so.9") for n in names)


def load_cuda():
    """Make cuBLAS/cuDNN findable by ctranslate2."""
    for d in cuda_dirs():
        if IS_WIN:
            _dll_handles.append(os.add_dll_directory(d))
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
        else:
            # ctranslate2 dlopens these by soname; preloading them globally satisfies that without LD_LIBRARY_PATH
            order = ("libcublasLt", "libcublas", "libnvrtc", "libcudnn")
            libs = sorted(glob.glob(os.path.join(d, "*.so*")),
                          key=lambda p: next((i for i, o in enumerate(order) if os.path.basename(p).startswith(o)), 9))
            for lib in libs:
                try:
                    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass
