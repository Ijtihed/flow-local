"""Persisted correction learning and field isolation; no real desktop or audio."""
import json
import contextlib
import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import learn
from memory import Memory
from ui import Api
from engine import Engine

class Learning(unittest.TestCase):
    def test_manual_word_and_confirmed_repair_are_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'memory.db'
            api = Api(); api._mem = Memory(path)
            api.add_term(' AsterByte ', ' AsterBytek ')
            self.assertEqual(api._mem.correct('Ask AsterBytek.'), 'Ask AsterByte.')
            api._mem.db.close()
            restarted = Memory(path)
            self.assertEqual(restarted.correct('Ask AsterBytek.'), 'Ask AsterByte.')
            restarted.db.close()

    def test_manual_word_validation_reports_unsaved_input(self):
        api = Api()
        for word, heard in [('', ''), (' '*3, ''), ('x'*61, ''), ('word', 'x'*121), ('bad\nword', ''), (None, '')]:
            with self.assertRaises(ValueError): api.add_term(word, heard)

    def test_personal_pass_repairs_suffix_spelling_with_crowded_vocabulary(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / 'memory.db')
            memory.add_term('AsterByte')
            for i in range(40): memory.add_term(f'LongSyntheticProjectNumber{i}')
            self.assertEqual(memory.core_terms(preferred=['AsterByte'])[0], 'AsterByte')
            self.assertIn('AsterByte', memory.candidates('I use AsterBytek.'))
            self.assertNotIn('AsterByte', memory.candidates('I use AsterByte.'))
            engine = Engine(memory)
            with patch.object(engine, 'pick_languages', return_value=(['en'],1.0)), patch.object(engine, '_mixed', return_value=None), patch.object(engine, '_decode', side_effect=[('I use AsterBytek.',-.1,'en'), ('I use AsterByte.',-.1,'en')]) as decode:
                text, language = engine.transcribe([], {'languages':['en'],'name':'AsterByte'})
            self.assertEqual(text, 'I use AsterByte.')
            self.assertEqual(language, 'en')
            self.assertTrue(decode.call_args.args[2].startswith('AsterByte,'))
            self.assertEqual(engine.finish(text, {'styles':{'personal':'very casual'}}, ('telegram','')), 'i use AsterByte')
            memory.db.close()

    def test_history_edit_teaches_future_dictation_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            before, after = 'Please ask Asterbite tomorrow.', 'Please ask AsterByte tomorrow.'
            history = path / 'history.jsonl'
            history.write_text(json.dumps({'ts':'fixture','text':before,'words':5})+'\n', 'utf-8')
            memory = Memory(path / 'memory.db')
            api = Api(); api._mem = memory
            with patch('ui.HISTORY', history):
                self.assertEqual(api.edit('fixture', after), ['Asterbite → AsterByte'])
                self.assertEqual(api.history()[0]['text'], after)
            memory.db.close()
            restarted = Memory(path / 'memory.db')
            self.assertEqual(restarted.correct(before), after)
            self.assertIn('AsterByte', restarted.core_terms())
            restarted.db.close()

    def test_case_only_fix_preserves_existing_use_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / 'memory.db')
            memory.add_term('asterbyte', 'you')
            memory.learn_dictation('asterbyte', 'en')
            memory.learn_correction('I use asterbyte.', 'I use AsterByte.')
            self.assertEqual(memory.correct('I use asterbyte.'), 'I use AsterByte.')
            row = next(t for t in memory.listing()['terms'] if t['text']=='AsterByte')
            self.assertEqual(row['uses'], 1); self.assertEqual(row['source'], 'you')
            memory.db.close()

    def test_automatic_fix_is_confirmed_after_two_independent_observations(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / 'memory.db')
            for attempt in range(2):
                with patch('learn.focused_text', side_effect=[('field', 'Please ask Asterbite tomorrow.'), ('field', 'Please ask AsterByte tomorrow.')]), patch('learn.CHECKS', (0,)):
                    notify = Mock()
                    learn.watch('Please ask Asterbite tomorrow.', memory, notify).join(2)
                    notify.assert_called_once()
                self.assertEqual(memory.listing()['fixes'][0]['active'], attempt == 1)
            self.assertEqual(memory.correct('Please ask Asterbite tomorrow.'), 'Please ask AsterByte tomorrow.')
            memory.db.close()

    def test_changed_or_inaccessible_field_does_not_teach_a_correction(self):
        for initial, later in [(('first','Please ask Asterbite tomorrow.'),('second','Please ask AsterByte tomorrow.')),
                               ((None,None),('second','Please ask AsterByte tomorrow.')),
                               (('first','Unrelated text'),('first','Please ask AsterByte tomorrow.'))]:
            with patch('learn.focused_text', side_effect=[initial,later]), patch('learn.CHECKS',(0,)):
                memory, notify = Mock(), Mock()
                learn.watch('Please ask Asterbite tomorrow.', memory, notify).join(2)
                memory.learn_correction.assert_not_called(); notify.assert_not_called()

    def test_rewording_is_not_learned_as_an_automatic_spelling_fix(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / 'memory.db')
            self.assertEqual(memory.learn_correction('The meeting is today.', 'The meeting is tomorrow.', auto=True), [])
            self.assertEqual(memory.listing()['fixes'], [])
            memory.db.close()

    def test_password_fields_are_never_read(self):
        field = Mock(); field.IsPassword = True
        automation = types.SimpleNamespace(GetFocusedControl=lambda:field,
            UIAutomationInitializerInThread=lambda **kwargs:contextlib.nullcontext())
        with patch('system.IS_WIN', True), patch.dict('sys.modules', {'uiautomation':automation}):
            self.assertEqual(learn.focused_text(), (None,None))
        field.GetValuePattern.assert_not_called(); field.GetTextPattern.assert_not_called()

    def test_identical_field_labels_have_distinct_runtime_identity(self):
        field = Mock(IsPassword=False, ProcessId=1, ControlTypeName='Edit', AutomationId='', Name='')
        field.GetValuePattern.return_value.Value = 'Please ask Asterbite tomorrow.'
        field.GetRuntimeId.side_effect = [[1,2], [1,3]]
        automation = types.SimpleNamespace(GetFocusedControl=lambda:field,
            UIAutomationInitializerInThread=lambda **kwargs:contextlib.nullcontext())
        with patch('system.IS_WIN', True), patch.dict('sys.modules', {'uiautomation':automation}):
            first, _ = learn.focused_text()
            second, _ = learn.focused_text()
        self.assertNotEqual(first, second)

if __name__ == '__main__': unittest.main()
