"""Hold/release reaches the real capture lifecycle without microphone access."""
import sys
import unittest
from collections import deque
from unittest.mock import MagicMock, patch

import numpy as np
from flow import Flow
from hotkeys_linux import Hotkeys, SHORTCUTS


class Release(unittest.TestCase):
    def fixture(self):
        flow = Flow.__new__(Flow)
        flow.ready = True
        flow.busy = flow.recording = False
        flow.practice = None
        flow.mode = None
        flow.state = "idle"
        flow.levels = deque(maxlen=20)
        flow.keys = MagicMock()
        flow.set_tray = MagicMock()
        return flow

    def capture(self, flow):
        stream = MagicMock()
        callback = []

        def create(**options):
            callback.append(options["callback"])
            return stream

        return stream, callback, patch("sounddevice.InputStream", side_effect=create)

    def test_release_closes_even_the_shortest_press_for_every_shortcut(self):
        for name, groups in SHORTCUTS.items():
            with self.subTest(shortcut=name):
                flow = self.fixture()
                hook = Hotkeys.__new__(Hotkeys)
                hook.groups = groups
                hook.held = set()
                hook.active = hook.recording = False
                hook.emit = flow.on_key
                flow.keys = hook
                stream, callbacks, capture = self.capture(flow)
                keys = [next(iter(group)) for group in groups]
                with capture, patch("flow.foreground_app", return_value=("test", "")):
                    for key in keys:
                        hook.handle(key, True)
                    self.assertTrue(flow.recording)
                    hook.handle(keys[-1], True)  # OS key repeat must not latch.
                    hook.handle(keys[-1], False)
                self.assertFalse(flow.recording)
                self.assertFalse(hook.recording)
                stream.stop.assert_called_once()
                stream.close.assert_called_once()

    def test_either_modifier_release_stops_the_chord(self):
        for release in ("lctrl", "lmeta"):
            flow = self.fixture()
            flow.start = lambda mode: (setattr(flow, "recording", True), setattr(flow, "mode", mode))
            flow.finish = lambda: setattr(flow, "recording", False)
            hook = Hotkeys.__new__(Hotkeys)
            hook.groups = SHORTCUTS["ctrl+win"]
            hook.held = set(); hook.active = hook.recording = False
            hook.emit = flow.on_key
            hook.handle("lctrl", True); hook.handle("lmeta", True)
            hook.handle(release, False)
            self.assertFalse(flow.recording)

    def test_two_quick_taps_never_enable_hands_free(self):
        flow = self.fixture()
        stream, _, capture = self.capture(flow)
        with capture, patch("flow.foreground_app", return_value=("test", "")):
            for _ in range(2):
                flow.on_key("down")
                flow.on_key("up")
                self.assertFalse(flow.recording)
                self.assertEqual(flow.mode, "ptt")
        self.assertEqual(stream.close.call_count, 2)

    def test_release_freezes_audio_before_transcription(self):
        flow = self.fixture()
        stream, callbacks, capture = self.capture(flow)
        audio = np.ones((16000, 1), np.float32) * .05
        with capture, patch("flow.foreground_app", return_value=("test", "")), patch("flow.threading.Thread") as worker:
            flow.on_key("down")
            callbacks[0](audio, len(audio), None, None)
            # PortAudio may deliver a final callback while stop is running.
            stream.stop.side_effect = lambda: callbacks[0](audio, len(audio), None, None)
            flow.on_key("up")
        self.assertFalse(flow.recording)
        self.assertTrue(flow.busy)
        self.assertEqual(flow.state, "transcribing")
        self.assertEqual(len(worker.call_args.kwargs["args"][0]), 16000)
        callbacks[0](audio, len(audio), None, None)
        self.assertEqual(len(flow.chunks), 1)

    def test_driver_failure_still_closes_and_clears_recording(self):
        flow = self.fixture()
        stream, callbacks, capture = self.capture(flow)
        with capture, patch("flow.foreground_app", return_value=("test", "")):
            flow.on_key("down")
            stream.stop.side_effect = RuntimeError("Disconnected microphone")
            flow.on_key("up")
        stream.close.assert_called_once()
        self.assertFalse(flow.recording)
        self.assertFalse(flow.keys.recording)
        callbacks[0](np.ones((10, 1)), 10, None, None)
        self.assertFalse(flow.chunks)

    def test_old_callback_cannot_feed_a_new_recording(self):
        flow = self.fixture()
        _, callbacks, capture = self.capture(flow)
        with capture, patch("flow.foreground_app", return_value=("test", "")):
            flow.on_key("down"); flow.on_key("up"); flow.on_key("down")
            callbacks[0](np.ones((10, 1)), 10, None, None)
            self.assertFalse(flow.chunks)
            callbacks[1](np.ones((10, 1)), 10, None, None)
            self.assertEqual(len(flow.chunks), 1)
            flow.on_key("up")

    def test_explicit_space_lock_and_escape_still_work(self):
        flow = self.fixture()
        stream, _, capture = self.capture(flow)
        with capture, patch("flow.foreground_app", return_value=("test", "")):
            flow.on_key("down"); flow.on_key("lock"); flow.on_key("up")
            self.assertTrue(flow.recording)
            flow.on_key("cancel")
        self.assertFalse(flow.recording)
        stream.close.assert_called_once()

    def test_changing_shortcut_emits_release_and_clears_held_keys(self):
        hook = Hotkeys.__new__(Hotkeys)
        hook.groups = SHORTCUTS["f8"]
        hook.held = {"f8"}; hook.active = True
        hook.emit = MagicMock()
        hook.set_shortcut("right ctrl")
        hook.emit.assert_called_once_with("up")
        self.assertFalse(hook.active)
        self.assertFalse(hook.held)

    @unittest.skipUnless(sys.platform == "win32", "Windows hook")
    def test_windows_hook_releases_all_shortcuts_and_ignores_repeat(self):
        from hotkeys_win import Hotkeys as WinKeys, SHORTCUTS as WinShortcuts
        for name, groups in WinShortcuts.items():
            with self.subTest(shortcut=name):
                hook = WinKeys.__new__(WinKeys)
                hook.groups = groups
                hook.held = set(); hook.active = hook.recording = False
                events = []; hook.emit = events.append
                keys = [next(iter(group)) for group in groups]
                with patch("hotkeys_win.user32.GetAsyncKeyState", return_value=0x8000), patch("hotkeys_win.tap"):
                    for key in keys: hook._handle(key, True)
                    hook._handle(keys[-1], True)
                    hook._handle(keys[-1], False)
                self.assertEqual(events, ["down", "up"])


if __name__ == "__main__":
    unittest.main()
