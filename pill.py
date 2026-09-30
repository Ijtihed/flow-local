"""The floating pill that shows Flow is listening. Drawing is shared; each OS has its own way to show it."""
import tkinter as tk

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import paths
import icons
from system import IS_WIN


class PillBase:
    """The listening pill, drawn with PIL (anti-aliased, soft shadow). Subclasses put it on screen."""

    SS = 3  # supersampling

    def __init__(self, root, scale):
        self.s = scale
        self.win = tk.Toplevel(root)
        self.win.title("Flow recording status")
        self.win.overrideredirect(True)
        self.win.geometry("1x1+0+0")
        self.win.update_idletasks()
        self.visible = False
        self.font = self._font(12)
        self.mark = icons.app_icon(round(16 * scale * self.SS))
        self.shadows = {}

    def _font(self, size):
        for name in ("SegUIVar.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
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
            ImageDraw.Draw(img).rounded_rectangle((m, m + m * 0.2, m + w, m + h + m * 0.2), r, fill=50)
            self.shadows[key] = img.filter(ImageFilter.GaussianBlur(m / 3))
        return self.shadows[key]

    def render(self, state, t, levels, message, appear, locked=False, elapsed=0):
        k = self.s * self.SS
        text_w = 0
        if state == "message":
            text_w = self.font.getlength(message) / k
        w_l = 224 if state != "message" else max(156, text_w + 56)
        h_l = 36
        # Keep geometry and text at their final size throughout a quick fade.
        e = 1 - (1 - max(0, min(1, appear))) ** 3
        W, H, M, R = int(w_l * k), int(h_l * k), int(10 * k), int(h_l * k / 2)
        img = Image.new("RGBA", (W + 2 * M, H + 2 * M), (0, 0, 0, 0))
        img.putalpha(self._shadow(W, H, M, R))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((M, M, M + W, M + H), R, fill=(255, 255, 255, 255), outline=(0, 0, 0, 40),
                            width=max(1, int(k)))
        cx, cy = M + W / 2, M + H / 2
        if e > 0:
            a = 255
            mark = self.mark.copy()
            mark.putalpha(mark.getchannel("A").point(lambda v: round(v * a / 255)))
            img.alpha_composite(mark, (int(M + 8 * k), int(cy - mark.height / 2)))
            cx += 10 * k
            if state == "listening":
                label_x = M + 32 * k
                d.text((label_x, cy), "Recording", font=self.font, fill=(29,29,31,a), anchor="lm")
                dx = label_x + self.font.getlength("Recording") + 6*k
                r = 2*k
                d.ellipse((dx-r,cy-r,dx+r,cy+r),fill=(239,68,68,a))
                d.text((M+W-10*k,cy), f"{int(elapsed)//60}:{int(elapsed)%60:02d}", font=self.font, fill=(85,85,90,a), anchor="rm")
                n, gap, bw = 9, 3.5 * k, 2 * k
                x0 = M + 144*k - (n - 1) * gap / 2
                for i in range(n):
                    lv = levels[-1] if levels else 0.0
                    env = 1 - abs(i - (n - 1) / 2) / ((n - 1) / 2) * 0.45
                    bh = round((3 + 16 * min(1.0, lv) * env) * self.s) * self.SS
                    x = round((x0 + i * gap) / self.SS) * self.SS
                    d.rounded_rectangle((x - bw / 2, cy - bh / 2, x + bw / 2, cy + bh / 2), bw / 2,
                                        fill=(22, 22, 24, a))
            elif state in ("transcribing", "polishing", "typing"):
                label = {"transcribing":"Thinking", "polishing":"Polishing", "typing":"Typing"}[state]
                if state == "transcribing" and elapsed >= 12:
                    label = "Still working"
                d.text((M+32*k,cy), label, font=self.font, fill=(29,29,31,a), anchor="lm")
                d.text((M+W-10*k,cy), f"{int(elapsed)}s",font=self.font,fill=(85,85,90,a),anchor="rm")
                n, gap, bw = 3, 8 * k, 3 * k
                x0 = M + 144*k - (n - 1) * gap / 2
                for i in range(n):
                    wave = 0.5 + 0.5 * np.sin(t * 6 - i * 0.7)
                    bh = 3 * k
                    x = x0 + i * gap
                    d.rounded_rectangle((x - bw / 2, cy - bh / 2, x + bw / 2, cy + bh / 2), bw / 2,
                                        fill=(22, 22, 24, int(a * (0.3 + 0.7 * wave))))
            else:
                d.text((cx, cy), message, font=self.font, fill=(29, 29, 31, a), anchor="mm")
        img = img.resize((img.width // self.SS, img.height // self.SS), Image.LANCZOS)
        if e < 1:
            img.putalpha(img.getchannel("A").point(lambda v: round(v * e)))
        self._blit(img)


if IS_WIN:
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("op", ctypes.c_byte), ("flags", ctypes.c_byte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_byte)]


    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]


    user32.GetParent.restype = wt.HWND
    user32.GetParent.argtypes = [wt.HWND]
    user32.GetForegroundWindow.restype = wt.HWND
    user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
    user32.MonitorFromWindow.restype = wt.HANDLE
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
    user32.SetWindowPos.restype = wt.BOOL
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
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

    class Pill(PillBase):
        """Per-pixel-alpha, click-through Win32 layered window fed with PIL frames."""

        def __init__(self, root):
            super().__init__(root, user32.GetDpiForSystem() / 96)
            self.hwnd = user32.GetParent(self.win.winfo_id())
            style = user32.GetWindowLongW(self.hwnd, -20)
            # layered | click-through | topmost | no taskbar button | never takes focus
            user32.SetWindowLongW(self.hwnd, -20, style | 0x80000 | 0x20 | 0x8 | 0x80 | 0x08000000)
            self.win.withdraw()
            self.monitor = None
            self.last_frame = None

        def show(self):
            if not self.visible:
                super().show()
                # Mapping a Tk window can set its uniform alpha again. Present
                # a fresh frame after mapping, without activating the window.
                if self.last_frame is not None:
                    self._blit(self.last_frame)
                self._raise()

        def _raise(self):
            # WS_EX_TOPMOST must be applied through SetWindowPos; setting the
            # extended-style bit alone does not change the actual z-order.
            if not user32.SetWindowPos(self.hwnd, wt.HWND(-1), 0, 0, 0, 0, 0x13):
                raise ctypes.WinError()

        def _position(self, w, h):
            if not self.visible or self.monitor is None:
                self.monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), 2)
            info = MONITORINFO(); info.cbSize = ctypes.sizeof(info)
            if user32.GetMonitorInfoW(self.monitor, ctypes.byref(info)):
                area = info.rcWork
                return area.left + (area.right - area.left - w) // 2, area.bottom - h - int(24 * self.s)
            return (user32.GetSystemMetrics(0) - w) // 2, user32.GetSystemMetrics(1) - h - int(64 * self.s)

        def _blit(self, img):
            self.last_frame = img
            w, h = img.size
            arr = np.asarray(img, dtype=np.uint16)
            alpha = arr[..., 3:4]
            bgra = np.empty((h, w, 4), np.uint8)
            bgra[..., :3] = (arr[..., [2, 1, 0]] * alpha // 255).astype(np.uint8)
            bgra[..., 3] = arr[..., 3]
            x, y = self._position(w, h)

            screen = user32.GetDC(None)
            mem = gdi32.CreateCompatibleDC(screen)
            bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            bits = ctypes.c_void_p()
            bmp = gdi32.CreateDIBSection(mem, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
            ctypes.memmove(bits, bgra.tobytes(), w * h * 4)
            old = gdi32.SelectObject(mem, bmp)
            blend = BLENDFUNCTION(0, 0, 255, 1)
            args = (self.hwnd, screen, ctypes.byref(wt.POINT(x, y)), ctypes.byref(wt.SIZE(w, h)),
                    mem, ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(blend), 2)
            accepted = user32.UpdateLayeredWindow(*args)
            if not accepted:
                # Tk uses SetLayeredWindowAttributes. Windows then refuses
                # per-pixel frames until WS_EX_LAYERED is cleared and restored.
                style = user32.GetWindowLongW(self.hwnd, -20)
                user32.SetWindowLongW(self.hwnd, -20, style & ~0x80000)
                user32.SetWindowLongW(self.hwnd, -20, style | 0x80000)
                accepted = user32.UpdateLayeredWindow(*args)
            error = ctypes.windll.kernel32.GetLastError() if not accepted else 0
            gdi32.SelectObject(mem, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, screen)
            if not accepted:
                raise ctypes.WinError(error)

else:
    from PIL import ImageTk

    class Pill(PillBase):
        """Linux: a Tk window cut to the pill's shape with the X Shape extension (XWayland too), click-through."""

        def __init__(self, root):
            super().__init__(root, max(1.0, root.winfo_fpixels("1i") / 96))
            self.win.attributes("-topmost", True)
            try:
                self.win.attributes("-type", "notification")
            except tk.TclError:
                pass
            self.label = tk.Label(self.win, bd=0, highlightthickness=0, bg="white")
            self.label.pack()
            self.win.withdraw()
            self.shape_key = None
            self.photo = None

        def _blit(self, img):
            alpha = img.getchannel("A")
            box = alpha.point(lambda v: 255 if v > 160 else 0).getbbox()
            if not box:
                return
            img = img.crop(box)
            mask = np.asarray(img.getchannel("A")) > 160
            flat = Image.new("RGB", img.size, (255, 255, 255))
            flat.paste(img, mask=img.getchannel("A"))
            self.photo = ImageTk.PhotoImage(flat)
            self.label.configure(image=self.photo)
            w, h = img.size
            sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
            self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - h - int(72 * self.s)}")
            key = (w, h, mask.sum())
            if key != self.shape_key:
                self.shape_key = key
                self._shape(mask)

        def _shape(self, mask):
            try:
                from Xlib import X, display
                from Xlib.ext import shape
                d = display.Display()
                self.win.update_idletasks()
                win = d.create_resource_object("window", int(self.win.wm_frame(), 16))
                rects = []
                for y, row in enumerate(mask):
                    xs = np.flatnonzero(row)
                    if xs.size:
                        rects.append((int(xs[0]), y, int(xs[-1] - xs[0] + 1), 1))
                win.shape_rectangles(shape.SO.Set, shape.SK.Bounding, X.Unsorted, 0, 0, rects)
                win.shape_rectangles(shape.SO.Set, shape.SK.Input, X.Unsorted, 0, 0, [])   # click-through
                d.sync()
                d.close()
            except Exception as e:
                print("pill shape:", e)
