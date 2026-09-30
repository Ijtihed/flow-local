"""Model switching, CPU fallback and spoken text expansion without any desktop access."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine import Engine
from memory import Memory
from flow import Flow
from ui import Api
import paths


class EngineSettings(unittest.TestCase):
    def test_full_gpu_chooses_cpu_before_loading_the_model(self):
        engine = Engine(MagicMock())
        model = MagicMock(); model.transcribe.return_value = (iter([]), MagicMock())
        with patch('engine.add_cuda_dlls'), patch('ctranslate2.get_cuda_device_count', return_value=1), patch('setup_tasks.cuda_ready', return_value=True), patch('setup_tasks.available_vram', return_value=.5), patch('setup_tasks.nvidia_gpu', return_value=('Test GPU', 12)), patch('faster_whisper.WhisperModel', return_value=model) as factory:
            engine.load('fixture-path', model_name='large-v3')
        self.assertEqual(factory.call_args.kwargs['device'], 'cpu')

    def test_cuda_inference_failure_falls_back_to_cpu(self):
        engine=Engine(None)
        bad=MagicMock();bad.transcribe.side_effect=RuntimeError("Unavailable GPU library")
        good=MagicMock();good.transcribe.return_value=(iter([]),None)
        with patch("engine.add_cuda_dlls"), patch("ctranslate2.get_cuda_device_count",return_value=1), patch("setup_tasks.cuda_ready",return_value=True), patch("faster_whisper.WhisperModel",side_effect=[bad,good]) as model:
            engine.load("isolated-model-path")
            self.assertEqual(engine.device,"cpu")
            self.assertEqual(model.call_args.kwargs["compute_type"],"int8")
            self.assertIs(engine.whisper,good)

    def test_shortcuts_expand_full_phrases_and_preserve_saved_case(self):
        with tempfile.TemporaryDirectory() as folder:
            memory=Memory(Path(folder)/"memory.db",["en"])
            engine=Engine(memory)
            settings={"styles":{"personal":"very casual"},"snippets":[{"trigger":"my email","text":"Alex@example.com"}]}
            self.assertEqual(engine.finish("My email.",settings,("telegram","Maya")),"Alex@example.com")
            self.assertEqual(engine.finish("My email address.",settings,("telegram","Maya")),"Alex@example.com address")
            self.assertEqual(engine.finish("my emailing",settings,("telegram","Maya")),"my emailing")
            memory.db.close()

    def test_reselecting_an_engine_changes_reload_signature(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(paths,"DATA",Path(folder)), patch.object(paths,"SETTINGS",Path(folder)/"settings.json"), patch("setup_tasks.find_model",return_value="isolated-model-path"), patch("setup_tasks.available_ram",return_value=8), patch("time.time_ns",return_value=1):
            api=Api();config={"provider":"local","model":"small"}
            api.configure_speech(config);a=Flow._speech_signature(paths.load_settings())
            api.configure_speech(config);b=Flow._speech_signature(paths.load_settings())
            self.assertNotEqual(a,b)

    def test_settings_do_not_change_during_dictation(self):
        flow=Flow.__new__(Flow);flow.recording=True;flow.busy=False
        with patch("flow.load_settings") as load:
            flow.reload();load.assert_not_called()
        flow.recording=False;flow.busy=True
        with patch("flow.load_settings") as load:
            flow.reload();load.assert_not_called()


if __name__ == "__main__": unittest.main()
