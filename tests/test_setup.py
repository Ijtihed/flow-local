"""Model setup must work even when inference has enabled offline mode."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paths
import setup_tasks


class Downloads(unittest.TestCase):
    def test_model_download_is_complete_and_does_not_change_active_engine(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(paths, "MODELS", Path(folder)):
            class Response:
                def __init__(self, url): self.url = url
                def raise_for_status(self): pass
                def json(self): return [{"type":"file", "path":p, "size":5} for p in ("config.json","model.bin","tokenizer.json")]
                def iter_content(self, *args): yield b"model"
                def __enter__(self): return self
                def __exit__(self, *args): pass
            with patch.dict(os.environ, {"HF_HUB_OFFLINE":"1"}), patch("requests.get", side_effect=lambda url, **kw: Response(url)) as get, patch.object(paths, "save_settings") as save:
                setup_tasks._download_model("small")
                self.assertEqual(get.call_count, 4)
                self.assertTrue(setup_tasks.find_model("small"))
                self.assertEqual({p.name for p in (Path(folder)/"small").iterdir()}, {"config.json","model.bin","tokenizer.json"})
                save.assert_not_called()

    def test_missing_repository_files_do_not_create_a_ready_model(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(paths, "MODELS", Path(folder)):
            with patch("requests.get") as get:
                get.return_value.json.return_value = [{"type":"file","path":"model.bin","size":10}]
                with self.assertRaises(RuntimeError): setup_tasks._download_model("small")
                self.assertFalse((Path(folder)/"small").exists())


if __name__ == "__main__": unittest.main()
