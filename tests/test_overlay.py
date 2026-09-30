"""Verify that the status renderer responds to sound and keeps icons visible."""
import unittest
import sys
from PIL import ImageChops
import icons
from pill import PillBase


class Overlay(unittest.TestCase):
    def renderer(self):
        p = PillBase.__new__(PillBase)
        p.s = 1
        p.font = p._font(12)
        p.mark = icons.app_icon(48)
        p.shadows = {}
        p._blit = lambda image: setattr(p, 'frame', image)
        return p

    def test_voice_changes_bars_without_moving_capsule(self):
        p = self.renderer()
        p.render('listening', 1, [0], '', 1, elapsed=2)
        quiet = p.frame.copy()
        p.render('listening', 1, [.85], '', 1, elapsed=2)
        self.assertEqual(quiet.size, p.frame.size)
        self.assertIsNotNone(ImageChops.difference(quiet.convert('RGB'), p.frame.convert('RGB')).getbbox())

    def test_thinking_changes_dots_while_waiting(self):
        p = self.renderer()
        p.render('transcribing', 0, [], '', 1, elapsed=2)
        first = p.frame.copy()
        p.render('transcribing', .3, [], '', 1, elapsed=2)
        self.assertIsNotNone(ImageChops.difference(first.convert('RGB'), p.frame.convert('RGB')).getbbox())

    def test_entrance_preserves_crisp_geometry_at_small_size(self):
        p = self.renderer()
        p.render('listening', 0, [.6], '', .25)
        entrance_size = p.frame.size
        p.render('listening', 0, [.6], '', 1)
        self.assertEqual(entrance_size, p.frame.size, 'Entrance must not scale text or resize the capsule')
        self.assertLess(p.frame.width, 260)
        self.assertLess(p.frame.height, 64)

    def test_tray_badge_has_contrast_on_both_taskbar_themes(self):
        for light in (False, True):
            icon = icons.tray('idle', 16, light)
            for background in ('black', 'white'):
                from PIL import Image
                image = Image.new('RGB', icon.size, background)
                image.paste(icon, mask=icon.getchannel('A'))
                dark, bright = image.convert('L').getextrema()
                self.assertLess(dark, 80)
                self.assertGreater(bright, 180)


@unittest.skipUnless(sys.platform == 'win32', 'Native Windows presentation')
class NativePopup(unittest.TestCase):
    def test_windows_accepts_frames_after_show_and_remap_without_taking_focus(self):
        import tkinter as tk
        from pill import Pill, user32, wt
        root = tk.Tk(); root.withdraw()
        try:
            p = Pill(root)
            for state in ('listening', 'transcribing', 'listening'):
                foreground = user32.GetForegroundWindow()
                p.render(state, 1, [.6], '', 1)
                p.show(); root.update()
                rect = wt.RECT()
                self.assertTrue(user32.IsWindowVisible(p.hwnd))
                self.assertTrue(user32.GetWindowRect(p.hwnd, __import__('ctypes').byref(rect)))
                self.assertGreater(rect.right-rect.left, 180)
                self.assertGreaterEqual(rect.bottom-rect.top, 48)
                self.assertTrue(user32.GetWindowLongW(p.hwnd, -20) & 0x8)
                active = user32.GetForegroundWindow()
                self.assertNotEqual(active, p.hwnd, 'Popup took keyboard focus')
                self.assertTrue(user32.GetWindowLongW(p.hwnd, -20) & 0x08000000)
                # Windows CI can start with no foreground window while Tk's
                # hidden root is being unmapped. There is no focus to preserve.
                if foreground:
                    self.assertEqual(active, foreground)
                p.hide(); root.update()
        finally:
            root.destroy()
