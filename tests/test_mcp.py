"""Protocol and isolation checks. No real user profile, recording or paid API."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paths
from mcp_server import FlowService, public, validate_settings, bounded_audio
from mcp_config import connection_config
from memory import Memory
from tools.check_mcp import check


class MCP(unittest.TestCase):
    def test_bounded_audio_matches_speech_decoder(self):
        import numpy as np
        from faster_whisper import decode_audio
        fixture = paths.APP / "assets/speech-check/practice.wav"
        np.testing.assert_array_equal(bounded_audio(fixture), decode_audio(str(fixture), sampling_rate=16000))

    def test_bounded_audio_rejects_duration_and_empty_audio(self):
        import wave
        with tempfile.TemporaryDirectory() as folder:
            for frames in (20000, 0):
                file = Path(folder) / "fixture.wav"
                with wave.open(str(file), "wb") as output:
                    output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
                    output.writeframes(b"\x00\x00" * frames)
                with self.assertRaises(ValueError): bounded_audio(file, seconds=1)

    def test_real_stdio_protocol_and_privacy(self):
        self.assertTrue(asyncio.run(check())["ok"])

    def test_validation_rejects_credentials_and_onboarding_bypass(self):
        for key in ("api_key", "update_key", "speech_provider", "tutorial_seen", "tutorial_version", "voice_notes", "snippets", "unexpected"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_settings({key: True})
        for patch_value in ({"languages": []}, {"shortcut": "anything"}, {"shortcut": []}, {"mood": {}}, {"cleanup": "yes"}, {"styles": {"invalid": "casual"}}, {"styles": {"work": []}}, {"name": "\n"}):
            with self.assertRaises(ValueError):
                validate_settings(patch_value)

    def test_partial_styles_preserve_other_categories(self):
        with patch.object(paths, "load_settings", return_value={"styles": paths.DEFAULT_STYLES}):
            result = validate_settings({"styles": {"work": "formal"}})["styles"]
            self.assertEqual(result["work"], "formal")
            self.assertEqual(result["email"], paths.DEFAULT_STYLES["email"])

    def test_readonly_service_rejects_writes_before_touching_the_backend(self):
        service = FlowService(api=object(), read_only=True)
        with self.assertRaises(ValueError): service.configure({"name": "Alex"})
        with self.assertRaises(ValueError): service.set_shortcut("mail", "alex@example.com")

    def test_credentials_are_redacted_recursively(self):
        self.assertEqual(public({"name": "Alex", "api_key": "secret", "nested": [{"token": "secret", "ready": True}]}),
                         {"name": "Alex", "nested": [{"ready": True}]})

    def test_vocabulary_cache_observes_another_mcp_process(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Memory(Path(folder)/"memory.db"), Memory(Path(folder)/"memory.db")
            try:
                first.terms()
                second.add_term("Ijtihed")
                self.assertIn("Ijtihed", [term[0] for term in first.terms()])
                second.remove_term("Ijtihed")
                self.assertNotIn("Ijtihed", [term[0] for term in first.terms()])
            finally:
                first.db.close(); second.db.close()

    def test_source_and_packaged_launch_recipes(self):
        with patch.object(paths, "FROZEN", False):
            config = connection_config(True)["mcpServers"]["flow"]
            self.assertIn("--mcp", config["args"]); self.assertIn("--read-only", config["args"])
        with patch.object(paths, "FROZEN", True), patch("mcp_config.sys.platform", "win32"), patch("mcp_config.sys.executable", "C:/Flow/Flow.exe"):
            config = connection_config()["mcpServers"]["flow"]
            self.assertTrue(config["command"].endswith("FlowMCP.exe")); self.assertEqual(config["args"], [])
        with patch.object(paths, "FROZEN", True), patch("mcp_config.sys.platform", "linux"), patch.dict("mcp_config.os.environ", {"APPIMAGE": "/tmp/Flow.AppImage"}):
            config = connection_config()["mcpServers"]["flow"]
            self.assertEqual(config["command"], "/tmp/Flow.AppImage"); self.assertEqual(config["args"], ["--mcp"])
