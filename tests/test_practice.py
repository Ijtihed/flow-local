"""Real capture callback wiring, practice verification, leases and UI completion guards."""
import json
import os
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import control
import paths
from flow import Flow
from ui import Api


class Practice(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        self.patches = [patch.object(paths, "DATA", self.data), patch.object(paths, "SETTINGS", self.data / "settings.json"),
                        patch("flow.DATA", self.data)]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def fixture(self):
        f = Flow.__new__(Flow)
        f.root = MagicMock(); f.pill = MagicMock(); f.keys = MagicMock(); f.tray = MagicMock()
        f.engine = MagicMock(); f.memory = MagicMock(); f.events = queue.Queue()
        f.settings = {"languages": ["fi"], "speech_provider": "local"}
        f.ready = True; f.busy = False; f.recording = False; f.loading = False
        f.state = "idle"; f.state_started = time.time(); f.mode = None; f.message = ""
        f.practice = None; f.compose_session = None; f.record_started = 0
        f._last_status = 0; f._last_error = ""; f.hide_at = 0; f.appear = 0; f.t = .1
        f.levels = []; f.level = 0; f.tap_pending = 0; f.reload = MagicMock(); f.set_tray = MagicMock()
        f.paste = MagicMock(); f.save = MagicMock()
        return f

    def open_practice(self):
        api = Api()
        with patch.object(api, '_ensure_tray'):
            practice = api.practice_open()
        return api, practice

    @staticmethod
    def input_stream(**kwargs):
        stream = MagicMock()
        stream.start.side_effect = lambda: kwargs['callback'](np.ones((16000, 1), np.float32) * .05, 16000, None, None)
        return stream

    def test_shortcut_records_practice_and_release_closes_capture_and_accepts_it(self):
        f = self.fixture()
        api, practice = self.open_practice()
        f.engine.transcribe.return_value = (practice['phrase'], practice['language'])
        with patch('system.foreground_pid', return_value=os.getpid()), \
                patch('sounddevice.InputStream', side_effect=self.input_stream), \
                patch('flow.foreground_app', return_value=('flow', '')), \
                patch('flow.threading.Thread') as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs['target'](*thread.call_args.kwargs['args'])
            f.on_key('down')
            self.assertTrue(f.recording)
            self.assertEqual(f.mode, 'practice-ptt')
            self.assertEqual(f.practice['id'], practice['id'])
            f.on_key('lock')
            self.assertEqual(f.mode, 'practice-ptt')
            f.on_key('up')
            self.assertFalse(f.recording)
            self.assertFalse(f.capture_gate.is_set())
            f.stream.stop.assert_called_once()
            f.stream.close.assert_called_once()
            f.tick()
            self.assertEqual(api.practice_status()['phase'], 'passed')
            f.on_key('down')  # A passed tutorial cannot become ordinary dictation.
            self.assertFalse(f.recording)
        f.engine.cleanup.assert_not_called()
        f.memory.learn_dictation.assert_not_called()
        f.paste.assert_not_called()
        f.save.assert_not_called()
        api.practice_complete()
        self.assertFalse(list(control.folder().glob('practice-window-*.json')))

    def test_windows_hook_routes_ctrl_windows_and_either_release_to_practice(self):
        if os.name != 'nt':
            self.skipTest('Windows keyboard hook')
        from hotkeys_win import Hotkeys, SHORTCUTS, VK
        for released in ('lwin', 'lctrl'):
            with self.subTest(released=released):
                f = self.fixture()
                api, practice = self.open_practice()
                f.engine.transcribe.return_value = (practice['phrase'], practice['language'])
                keys = Hotkeys.__new__(Hotkeys)
                keys.emit = f.events.put
                keys.groups = SHORTCUTS['ctrl+win']
                keys.held = set()
                keys.active = keys.recording = False
                f.keys = keys
                with patch('hotkeys_win.user32.GetAsyncKeyState', return_value=0x8000), \
                        patch('hotkeys_win.tap'), patch('system.foreground_pid', return_value=os.getpid()), \
                        patch('sounddevice.InputStream', side_effect=self.input_stream), \
                        patch('flow.foreground_app', return_value=('flow', '')), \
                        patch('flow.threading.Thread') as thread:
                    thread.return_value.start.side_effect = lambda: thread.call_args.kwargs['target'](*thread.call_args.kwargs['args'])
                    keys._handle(VK['lctrl'], True)
                    keys._handle(VK['lwin'], True)
                    keys._handle(VK['lwin'], True)  # Holding cannot start a second stream.
                    f.tick()
                    self.assertTrue(f.recording)
                    self.assertEqual(f.mode, 'practice-ptt')
                    keys._handle(VK[released], False)
                    f.tick()
                    self.assertFalse(f.recording)
                    self.assertEqual(api.practice_status()['phase'], 'passed')
                    f.save.assert_not_called()
                    f.paste.assert_not_called()
                api.practice_complete()

    def test_background_tutorial_does_not_capture_other_apps_shortcut(self):
        f = self.fixture()
        api, practice = self.open_practice()
        api.practice_focus(False)
        f.start = MagicMock()
        with patch('system.foreground_pid', return_value=os.getpid() + 1):
            f.on_key('down')
        f.start.assert_called_once_with('ptt')
        self.assertIsNone(f.practice)

    def test_linux_tab_focus_and_windows_process_focus_select_only_the_live_tutorial(self):
        api, practice = self.open_practice()
        for native in (False, True):
            with self.subTest(native=native), patch('system.IS_WIN', native), \
                    patch('system.foreground_pid', return_value=os.getpid()):
                api.practice_focus(True)
                self.assertEqual(control.focused_practice(), {k: practice[k] for k in ('id', 'language', 'phrase')})
                with patch('system.foreground_pid', return_value=os.getpid() + 1):
                    api.practice_focus(False)
                    self.assertIsNone(control.focused_practice())
        with patch('control.time.time', return_value=time.time() + 7):
            self.assertIsNone(control.focused_practice())

    def test_closing_tutorial_unregisters_shortcut_and_cancels_capture(self):
        f = self.fixture()
        api, practice = self.open_practice()
        f.practice = practice
        f.recording = True
        f.mode = 'practice-ptt'
        f.stream = MagicMock()
        f.record_started = time.time()
        api.practice_close()
        f.tick()
        self.assertFalse(f.recording)
        self.assertIsNone(control.focused_practice())

    def test_shortcut_can_retry_after_cancellation_or_interruption(self):
        f = self.fixture()
        api, practice = self.open_practice()
        with patch('system.foreground_pid', return_value=os.getpid()), \
                patch('sounddevice.InputStream', side_effect=self.input_stream), \
                patch('flow.foreground_app', return_value=('flow', '')):
            for event in ('cancel', 'interrupt'):
                f.on_key('down')
                self.assertTrue(f.recording)
                f.on_key(event)
                self.assertFalse(f.recording)
                self.assertEqual(api.practice_status()['phase'], 'retry')
        f.save.assert_not_called()

    def test_shortcut_release_does_not_stop_a_button_started_practice(self):
        f = self.fixture()
        f.practice = {'id': 'a' * 32}
        f.recording = True
        f.mode = 'practice'
        f.finish = MagicMock()
        f.on_key('up')
        f.finish.assert_not_called()

    def test_matches_requires_all_spoken_words_and_ignores_punctuation(self):
        expected = control.PHRASES["en"]
        self.assertTrue(control.matches("I CAN SPEAK INSTEAD OF TYPING!", expected))
        self.assertFalse(control.matches("I can speak", expected))
        self.assertFalse(control.matches("I can type instead of speaking.", expected))
        self.assertFalse(control.matches("", expected))
        self.assertTrue(control.matches("يمكنني التحدث بدلا من الكتابة", control.PHRASES["ar"]))

    def test_backend_completion_cannot_be_skipped_or_saved_as_a_setting(self):
        api = Api()
        with patch.object(api, "_ensure_tray"):
            practice = api.practice_open()
        with self.assertRaises(ValueError): api.practice_complete()
        with self.assertRaises(ValueError): api.save_settings({"tutorial_seen": True})
        control.practice_result(practice["id"], matched=True, text="Wrong sentence")
        with self.assertRaises(ValueError): api.practice_complete()
        control.practice_result(practice["id"], matched=True, text=practice["phrase"].upper())
        api.practice_complete()
        self.assertEqual(paths.load_settings()["tutorial_version"], control.TUTORIAL_VERSION)
        self.assertFalse(control.result_path(practice["id"]).exists())

    def test_capture_transcription_and_acceptance_without_learning_or_paste(self):
        f = self.fixture(); api = Api()
        with patch.object(api, "_ensure_tray"):
            practice = api.practice_open()
        control.publish({"phase":"idle", "ready":True, "busy":False, "recording":False})
        # The microphone callback receives PCM, not a typed transcript. Hardware
        # input and engine inference are replaced with fixtures in this test.
        def input_stream(**kw):
            stream = MagicMock()
            stream.start.side_effect = lambda: kw["callback"](np.ones((16000,1),np.float32)*.05,16000,None,None)
            return stream
        f.engine.transcribe.return_value = (practice["phrase"], practice["language"])
        with patch("sounddevice.InputStream",side_effect=input_stream), patch("flow.foreground_app",return_value=("flow","")), patch("flow.threading.Thread") as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs["target"](*thread.call_args.kwargs["args"])
            api.practice_start(); f.tick()
            self.assertTrue(f.recording)
            self.assertEqual(api.practice_status()["phase"],"recording")
            api.practice_stop(); f.tick()
        self.assertFalse(f.recording); self.assertFalse(f.busy)
        self.assertEqual(api.practice_status()["phase"],"passed")
        self.assertEqual(f.engine.transcribe.call_args.args[1]["languages"],[practice["language"]])
        f.engine.cleanup.assert_not_called();f.memory.learn_dictation.assert_not_called()
        f.paste.assert_not_called();f.save.assert_not_called()
        api.practice_complete()

    def test_wrong_transcript_does_not_unlock_the_tutorial(self):
        f = self.fixture();ident = "a"*32
        f.practice={"id":ident,"language":"en","phrase":control.PHRASES["en"]};f.busy=True
        f.events.put(("practice_done",ident,"This is the wrong sentence."));f.tick()
        self.assertFalse(control.result(ident)["matched"])
        self.assertEqual(control.result(ident)["phase"],"retry")

    def test_closing_the_window_cancels_a_live_practice_recording(self):
        f = self.fixture();ident = "b"*32
        f.practice={"id":ident,"language":"en","phrase":control.PHRASES["en"]}
        f.recording=True;f.mode="practice";f.stream=MagicMock();f.record_started=time.time()
        f.tick()
        f.stream.stop.assert_called_once();f.stream.close.assert_called_once()
        self.assertFalse(f.recording)
        self.assertEqual(control.result(ident)["phase"],"retry")

    def test_capture_stops_after_fifteen_seconds(self):
        f = self.fixture();ident = "c"*32
        f.practice={"id":ident,"language":"en","phrase":control.PHRASES["en"]}
        f.recording=True;f.mode="practice";f.record_started=time.time()-16
        control.lease(ident);f.finish=MagicMock();f.tick();f.finish.assert_called_once()

    def test_cancelled_processing_cannot_later_mark_a_practice_as_passed(self):
        f = self.fixture();ident = "d"*32
        f.practice={"id":ident,"language":"en","phrase":control.PHRASES["en"]};f.busy=True
        f.cancel();f.events.put(("practice_done",ident,control.PHRASES["en"]));f.tick()
        self.assertFalse(control.result(ident)["matched"])
        self.assertFalse(f.busy)

    def test_stale_or_malformed_commands_are_ignored(self):
        folder=control.folder()/"commands"
        control.atomic_json(folder/"a.json",{"created":time.time()-11,"action":"record_start","args":{}})
        control.atomic_json(folder/"b.json",{"created":"not a time","args":{}})
        control.atomic_json(folder/"c.json",[])
        control.send("record_cancel",id="e"*32)
        self.assertEqual([x["action"] for x in control.commands()],["record_cancel"])
        self.assertFalse(control.commands())

    def test_recording_state_does_not_claim_a_stopped_engine_is_ready(self):
        control.publish({"phase":"idle","ready":True})
        self.assertTrue(control.state()["alive"])
        with patch("control.time.time",return_value=time.time()+6):
            self.assertFalse(control.state()["ready"])

    def test_home_recording_does_not_paste_into_another_app(self):
        f = self.fixture();f.mode="compose";f.settings["learn"]=True
        f.events.put(("done","A new thought.",1.2,"en",.4));f.tick()
        f.paste.assert_not_called();f.save.assert_called_once()

    def test_failed_paste_does_not_monitor_an_unrelated_field(self):
        f = self.fixture();f.mode='ptt';f.settings['learn']=True;f.paste.return_value=False
        with patch('flow.learn.watch') as watch:
            f.events.put(('done','A new thought.',1.2,'en',.4));f.tick()
            watch.assert_not_called()

    def test_audio_meter_smooths_changes_without_stalling_recording(self):
        f=self.fixture();f.recording=True;f.mode='hands';f.record_started=time.time();f.level=.05
        target=min(1,(f.level*14)**.8)
        f.tick();first=f.levels[-1]
        self.assertGreater(first,0);self.assertLess(first,target)
        for _ in range(8): f.tick()
        peak=f.levels[-1];self.assertGreater(peak,first);self.assertLess(peak,target)
        f.level=0;f.tick()
        self.assertGreater(f.levels[-1],0);self.assertLess(f.levels[-1],peak)
        self.assertTrue(f.recording)
