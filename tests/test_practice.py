"""Real capture callback wiring, practice verification, leases and UI completion guards."""
import json
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
