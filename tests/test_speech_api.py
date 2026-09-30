"""API contracts, consent and secret handling without sending any audio externally."""
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import paths
import speech_api
from ui import Api


class SpeechApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(paths, name, root / filename) for name, filename in
                        (("DATA", ""), ("SETTINGS", "settings.json"), ("MODELS", "models"))]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def config(self, **extra):
        return {"provider": "api", "base": "https://api.openai.com/v1", "model": "gpt-transcribe",
                "key": "test-key-never-real", "consent": True, **extra}

    def test_consent_key_storage_and_provider_change(self):
        api = Api()
        with self.assertRaises(ValueError): api.configure_speech(self.config(consent=False))
        self.assertFalse((paths.DATA / "speech-key").exists())
        api.configure_speech(self.config())
        self.assertTrue(speech_api.configured(paths.load_settings()))
        self.assertEqual(speech_api.get_key(), "test-key-never-real")
        self.assertNotIn("test-key", paths.SETTINGS.read_text())
        if os.name == "nt":
            self.assertNotIn(b"test-key", (paths.DATA / "speech-key").read_bytes())
        else:
            self.assertEqual((paths.DATA / "speech-key").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            api.configure_speech(self.config(key="", base="https://another.example/v1"))
        api.forget_api_key()
        self.assertFalse(speech_api.get_key())
        self.assertFalse(paths.load_settings()["api_consent"])

    def test_rejects_unsafe_urls_and_direct_settings_bypass(self):
        for value in ("http://api.example/v1", "https://user:pass@api.example/v1", "file:///tmp", "https://api.example/v1?key=secret"):
            with self.assertRaises(ValueError): speech_api.validated_base(value)
        self.assertEqual(speech_api.validated_base("http://127.0.0.1:1234/v1/"), "http://127.0.0.1:1234/v1")
        for field in ("api_key", "api_consent", "speech_provider", "model"):
            with self.assertRaises(ValueError): Api().save_settings({field: "anything"})

    def test_real_http_wav_contract(self):
        captured = {}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                captured.update(path=self.path, auth=self.headers.get("Authorization"),
                                body=self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"text":"Please send the project notes."}')
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            Api().configure_speech(self.config(base=f"http://127.0.0.1:{server.server_port}/v1"))
            text, lang = speech_api.transcribe(np.full(1600, .25, np.float32), paths.load_settings())
            self.assertEqual(text, "Please send the project notes.")
            self.assertEqual(lang, "en")
            self.assertEqual(captured["path"], "/v1/audio/transcriptions")
            self.assertEqual(captured["auth"], "Bearer test-key-never-real")
            body = captured["body"]
            self.assertIn(b"gpt-transcribe", body)
            wav_at = body.index(b"RIFF")
            with wave.open(io.BytesIO(body[wav_at:]), "rb") as wav:
                self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()), (16000, 1, 2, 1600))
            self.assertNotIn(b"history", body)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_limits_errors_and_no_upload_without_consent(self):
        settings = paths.load_settings()
        with patch.object(speech_api.requests, "post") as post:
            with self.assertRaises(speech_api.SpeechError): speech_api.transcribe(np.zeros(16000), settings)
            post.assert_not_called()
        Api().configure_speech(self.config())
        settings = paths.load_settings()
        for code in (302, 401, 403, 429, 500):
            with patch.object(speech_api.requests, "post") as post:
                post.return_value.status_code = code
                with self.assertRaises(speech_api.SpeechError): speech_api.transcribe(np.zeros(160), settings)
                self.assertFalse(post.call_args.kwargs["allow_redirects"])
        with patch.object(speech_api.requests, "post", side_effect=speech_api.requests.Timeout):
            with self.assertRaisesRegex(speech_api.SpeechError, "timed out"):
                speech_api.transcribe(np.zeros(160), settings)


if __name__ == "__main__": unittest.main()
