"""Model setup must work even when inference has enabled offline mode."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import paths
import setup_tasks


class Downloads(unittest.TestCase):
    def test_recommendation_uses_free_vram_and_ram_with_headroom(self):
        gpu = ('Test GPU', 12)
        self.assertEqual(setup_tasks.recommended_model(gpu, 8, 12), 'large-v3')
        self.assertEqual(setup_tasks.recommended_model(gpu, 3.5, 8), 'large-v3-turbo')
        self.assertEqual(setup_tasks.recommended_model(gpu, 1.7, 8), 'small')
        self.assertEqual(setup_tasks.recommended_model(gpu, .5, 8), 'small')
        self.assertEqual(setup_tasks.recommended_model(gpu, 8, 3), 'small')
        self.assertIsNone(setup_tasks.recommended_model(gpu, 8, 1))
        self.assertEqual(setup_tasks.recommended_model(None, None, 8), 'small')

    def test_insufficient_ram_blocks_download_before_starting_a_thread(self):
        with patch.object(setup_tasks, 'available_ram', return_value=2.5), patch.object(setup_tasks.threading, 'Thread') as thread:
            with self.assertRaisesRegex(ValueError, 'free RAM'):
                setup_tasks.run('model', 'large-v3')
            thread.assert_not_called()

    def test_model_options_are_cpu_only_on_a_full_gpu_and_disable_low_ram(self):
        with patch.object(setup_tasks, 'nvidia_gpu', return_value=('Test GPU', 12)), patch.object(setup_tasks, 'available_vram', return_value=.5), patch.object(setup_tasks, 'available_ram', return_value=3), patch.object(setup_tasks, 'find_model', return_value=None):
            info = setup_tasks.hardware_models()
        self.assertEqual(info['recommended_model'], 'small')
        self.assertFalse(any(m['gpu_ok'] for m in info['models']))
        self.assertEqual([m['id'] for m in info['models'] if m['supported']], ['small'])

    def test_unknown_memory_is_marked_unverified(self):
        with patch.object(setup_tasks, 'nvidia_gpu', return_value=None), patch.object(setup_tasks, 'available_ram', return_value=None), patch.object(setup_tasks, 'find_model', return_value=None):
            info = setup_tasks.hardware_models()
        self.assertEqual(info['recommended_model'], 'small')
        self.assertTrue(all(not m['memory_known'] for m in info['models']))

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
