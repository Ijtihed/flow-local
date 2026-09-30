import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import health
import paths
from flow import Flow
from ui import Api


class SpeechHealth(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.patches=[patch.object(paths,'DATA',self.root),patch.object(paths,'APP',self.root),patch('flow.DATA',self.root)]
        for item in self.patches:item.start()
        folder=self.root/'assets/speech-check';folder.mkdir(parents=True)
        self.text='Open GitHub and share the download with the business team.'
        (folder/'manifest.json').write_text(json.dumps({'fixtures':[{'id':'business','file':'test.wav','text':self.text,'required':['github','download','business']}]}))
        with wave.open(str(folder/'test.wav'),'wb') as wav:
            wav.setparams((1,2,16000,0,'NONE','not compressed'))
            wav.writeframes((np.ones(16000,dtype=np.int16)*500).tobytes())
        self.settings={'speech_provider':'local','model':'small'}
        self.engine=MagicMock(device='cpu')

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def run_probe(self,text):
        with patch('engine.Engine') as cls:
            cls.return_value.transcribe.return_value=(text,'en')
            report=health.check(self.engine,self.settings)
            audio,settings=cls.return_value.transcribe.call_args.args
            self.assertEqual(audio.dtype,np.float32)
            self.assertEqual(settings['languages'],['en'])
            self.assertEqual(len(audio),16000)
            return report

    def test_known_audio_runs_through_engine_and_passes_without_user_memory(self):
        report=self.run_probe(self.text)
        self.assertEqual(report['status'],'passed')
        self.assertEqual(report['checks'][0]['word_error_rate'],0)
        self.engine.memory.learn_dictation.assert_not_called()

    def test_missing_important_word_fails_even_with_low_overall_error_rate(self):
        report=self.run_probe(self.text.replace('GitHub','GitLab'))
        self.assertEqual(report['status'],'failed')
        self.assertLess(report['checks'][0]['word_error_rate'],.2)

    def test_empty_or_unrelated_transcript_fails(self):
        self.assertEqual(self.run_probe('')['status'],'failed')
        self.assertEqual(self.run_probe('Something unrelated')['status'],'failed')

    def test_word_errors_allow_punctuation_and_brand_spacing(self):
        self.assertEqual(health.error_rate('Open GitHub.','open git hub'),0)
        self.assertEqual(health.error_rate('Use ChatGPT','use Chat GPT!'),0)
        self.assertEqual(health.error_rate('a b c','a c'),1/3)

    def test_model_failure_report_does_not_contain_exception_secrets_or_paths(self):
        secret=r'C:\Users\private-person\secret-token'
        with patch('engine.Engine',side_effect=RuntimeError(secret)):
            report=health.check(self.engine,{**self.settings,'api_key':secret,'name':secret})
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['error_type'],'RuntimeError')
        self.assertNotIn(secret,json.dumps(report))
        health.failed_load(self.settings,RuntimeError(secret))
        self.assertNotIn(secret,json.dumps(health.current()))

    def test_api_startup_does_not_upload_or_incur_a_paid_request(self):
        with patch('speech_api.transcribe') as upload:
            report=health.check(self.engine,{'speech_provider':'api','api_model':'transcribe-model'})
        self.assertEqual(report['status'],'not_run')
        upload.assert_not_called()

    def test_report_is_exported_only_when_requested_and_version_is_checked(self):
        report=self.run_probe(self.text);health.save(report)
        api=Api();self.assertEqual(api.diagnostics()['status'],'passed')
        self.assertFalse((self.root/'Reports').exists())
        file=Path(api.export_speech_report())
        self.assertTrue(file.is_relative_to(self.root/'Reports'))
        self.assertEqual(json.loads(file.read_text()),report)
        with patch('system.copy_text') as copy:
            api.copy_speech_report();self.assertEqual(json.loads(copy.call_args.args[0]),report)
        health.save({**report,'version':'old'})
        self.assertEqual(health.current()['status'],'checking')

    def test_startup_failed_check_warns_but_does_not_hide_a_loaded_engine(self):
        f=Flow.__new__(Flow);f.engine=self.engine;f.memory=MagicMock();f.events=MagicMock();f.loading=True
        settings={**self.settings,'onboarded':True,'languages':['en'],'cleanup':False}
        with patch('flow.load_settings',return_value=settings),patch('setup_tasks.find_model',return_value='fixture-model'),patch('setup_tasks.nvidia_gpu',return_value=None),patch('health.check',return_value={'status':'failed'}),patch('health.save'):
            f.load_model()
        self.engine.load.assert_called_once_with('fixture-model')
        messages=[call.args[0] for call in f.events.put.call_args_list]
        self.assertIn('ready',messages);self.assertIn('health_warning',messages)
        self.assertFalse(f.loading)
