"""Update selection, integrity, credentials, retries and data-preserving replacement."""
import hashlib
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import paths
import updates
from ui import Api


class Response:
    def __init__(self, data=None, content=b'', status=200, headers=None):
        self.data, self.content, self.status_code = data, content, status
        self.headers = headers or {}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def json(self): return self.data
    def iter_content(self, size):
        yield self.content[:3]
        yield self.content[3:]


class Updates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.data = patch.object(paths, 'DATA', self.folder)
        self.data.start()
        self.payload = b'new installer payload'
        self.asset = {'name': 'FlowSetup.exe', 'size': len(self.payload), 'id': 123,
                      'version': '1.6.0', 'sha256': hashlib.sha256(self.payload).hexdigest()}
    def tearDown(self):
        self.data.stop()
        self.tmp.cleanup()
    def release(self, tag='v1.6.0', **asset):
        return {'tag_name': tag, 'draft': False, 'prerelease': False,
                'assets': [{**self.asset, 'state': 'uploaded', 'digest': 'sha256:' + self.asset['sha256'], **asset}]}

    def test_only_new_stable_complete_releases_are_selected(self):
        with patch.object(updates.sys, 'platform', 'win32'), patch.object(updates.requests, 'get', return_value=Response(self.release())):
            self.assertEqual(updates.latest('')['version'], '1.6.0')
        for tag in ('v1.0.0', 'v' + updates.APP_VERSION):
            with patch.object(updates.requests, 'get', return_value=Response(self.release(tag))):
                self.assertIsNone(updates.latest(''))
        for value in ('v1.6.0-beta', 'latest', '../../anything', None):
            with self.assertRaises(updates.UpdateError): updates.version(value)
        for extra in ({'digest': None}, {'size': 0}, {'id': '123'}, {'state': 'new'}):
            with patch.object(updates.sys, 'platform', 'win32'), patch.object(updates.requests, 'get', return_value=Response(self.release(**extra))):
                with self.assertRaises(updates.UpdateError): updates.latest('')
        release = self.release(); release['prerelease'] = True
        with patch.object(updates.requests, 'get', return_value=Response(release)):
            with self.assertRaises(updates.UpdateError): updates.latest('')

    def test_linux_selects_appimage_not_windows_installer(self):
        release = self.release()
        release['assets'].append({**release['assets'][0], 'name': 'Flow-x86_64.AppImage'})
        with patch.object(updates.sys, 'platform', 'linux'), patch.object(updates.requests, 'get', return_value=Response(release)):
            self.assertEqual(updates.latest('')['name'], 'Flow-x86_64.AppImage')

    def test_private_access_error_is_useful_and_never_contains_token(self):
        for status in (401, 403, 404, 500):
            with patch.object(updates.requests, 'get', return_value=Response(status=status)) as get:
                with self.assertRaises(updates.UpdateError) as error: updates.latest('private-dummy-token')
                self.assertNotIn('private-dummy-token', str(error.exception))
                self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer private-dummy-token')
                self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_verified_download_and_progress(self):
        progress = []
        with patch.object(updates.requests, 'get', return_value=Response(content=self.payload)):
            file = updates.download(self.asset, '', lambda done, total: progress.append((done, total)))
        self.assertEqual(file.read_bytes(), self.payload)
        self.assertEqual(progress[-1], (len(self.payload), len(self.payload)))
        self.assertFalse(file.with_suffix('.partial').exists())

    def test_bad_download_does_not_replace_existing_verified_file(self):
        target = self.folder/'updates/1.6.0/FlowSetup.exe'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'previous verified installer')
        for body in (b'truncated', b'x' * len(self.payload), self.payload + b'oversized'):
            with patch.object(updates.requests, 'get', return_value=Response(content=body)):
                with self.assertRaises(updates.UpdateError): updates.download(self.asset, '', lambda *a: None)
            self.assertEqual(target.read_bytes(), b'previous verified installer')
            self.assertFalse(target.with_suffix('.partial').exists())

    def test_signed_asset_redirect_never_receives_github_authorization(self):
        responses = [Response(status=302, headers={'Location': 'https://release-assets.githubusercontent.com/a?signature=x'}), Response(content=self.payload)]
        with patch.object(updates.requests, 'get', side_effect=responses) as get:
            updates.download(self.asset, 'private-dummy-token', lambda *a: None)
        self.assertIn('Authorization', get.call_args_list[0].kwargs['headers'])
        self.assertNotIn('headers', get.call_args_list[1].kwargs)
        for location in ('https://attacker.example/a', 'http://objects.githubusercontent.com/a', 'https://user@objects.githubusercontent.com/a'):
            with patch.object(updates.requests, 'get', return_value=Response(status=302, headers={'Location': location})) as get:
                with self.assertRaises(updates.UpdateError): updates.download(self.asset, 'dummy', lambda *a: None)
                self.assertEqual(get.call_count, 1)

    def test_access_storage_is_separate_from_speech_and_settings(self):
        updates.save_token('dummy-github-token')
        self.assertEqual(updates.token(), 'dummy-github-token')
        self.assertFalse((self.folder/'speech-key').exists())
        self.assertFalse((self.folder/'settings.json').exists())
        if os.name == 'nt':
            self.assertNotIn(b'dummy-github-token', (self.folder/'update-key').read_bytes())
        else:
            self.assertEqual((self.folder/'update-key').stat().st_mode & 0o777, 0o600)
        self.assertNotIn('dummy-github-token', str(updates.Manager().status()))
        Api().forget_update_access()
        self.assertFalse((self.folder/'update-key').exists())

    def test_check_is_asynchronous_and_rejects_duplicate_work(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        manager = updates.Manager()
        def latest(access):
            started.set(); release.wait(5); return self.asset
        with patch.object(updates, 'token', return_value='dummy'), patch.object(updates, 'latest', side_effect=latest), patch.object(updates, 'publisher', return_value=True):
            original_set = manager._set
            def set_state(**values):
                original_set(**values)
                if values.get('phase') == 'available': finished.set()
            manager._set = set_state
            self.assertTrue(manager.check()); self.assertTrue(started.wait(2))
            self.assertEqual(manager.status()['phase'], 'checking')
            self.assertFalse(manager.check())
            release.set(); self.assertTrue(finished.wait(2))
            self.assertEqual(manager.status()['latest'], '1.6.0')
            self.assertTrue(manager.status()['publisher'])

    def test_install_refuses_to_interrupt_dictation(self):
        manager = updates.Manager(); manager.asset = self.asset; manager._set(phase='available')
        with patch('control.state', return_value={'recording': True}), patch.object(updates, 'download') as download:
            with self.assertRaises(updates.UpdateError): manager.apply(Mock())
            download.assert_not_called()

    def test_install_callback_only_runs_after_verified_download_and_handoff(self):
        manager = updates.Manager(); manager.asset = self.asset; manager._set(phase='available')
        complete = threading.Event()
        file = self.folder/'installer.exe'
        with patch('control.state', return_value={}), patch.object(updates, 'token', return_value='dummy'), patch.object(updates, 'download', return_value=file), patch.object(updates, 'install') as install:
            self.assertTrue(manager.apply(complete.set))
            self.assertTrue(complete.wait(2))
            install.assert_called_once_with(file)
            self.assertEqual(manager.status()['phase'], 'installing')

    def test_failed_download_keeps_app_running_and_allows_retry(self):
        manager = updates.Manager(); manager.asset = self.asset; manager._set(phase='available')
        complete = threading.Event(); close = Mock()
        original = manager._set
        def set_state(**values):
            original(**values)
            if values.get('phase') == 'error': complete.set()
        manager._set = set_state
        with patch('control.state', return_value={}), patch.object(updates, 'token', return_value='dummy'), patch.object(updates, 'download', side_effect=updates.UpdateError('Integrity check failed.')), patch.object(updates, 'install') as install:
            self.assertTrue(manager.apply(close)); self.assertTrue(complete.wait(2))
            install.assert_not_called(); close.assert_not_called()
            self.assertEqual(manager.status()['phase'], 'error')
            self.assertEqual(manager.status()['message'], 'Integrity check failed.')

    def test_linux_replacement_is_atomic_with_backup_and_preserves_data(self):
        target = self.folder/'Flow.AppImage'; target.write_bytes(b'old version'); target.chmod(0o755)
        settings = self.folder/'settings.json'; settings.write_bytes(b'personal settings')
        file = self.folder/'new.AppImage'; file.write_bytes(b'new version')
        updates.linux_replace(file, target)
        self.assertEqual(target.read_bytes(), b'new version')
        self.assertEqual(target.with_name('Flow.AppImage.previous').read_bytes(), b'old version')
        self.assertEqual(settings.read_bytes(), b'personal settings')
        if os.name != 'nt':
            self.assertTrue(target.stat().st_mode & 0o100)

    def test_windows_helper_scopes_process_wait_preserves_startup_and_quotes_paths(self):
        text = updates.windows_script(Path("C:/O'Brien/FlowSetup.exe"), Path('C:/First Last/Flow/Flow.exe'), False)
        self.assertIn(str(Path("C:/O'Brien/FlowSetup.exe")).replace("'", "''"), text)
        self.assertIn('$_.ExecutablePath -eq $flowExe', text)
        self.assertIn("'/TASKS='", text)
        self.assertIn('WindowStyle Hidden', text)
        self.assertNotIn('Remove-Item', text)
        self.assertNotIn('taskkill', text)
        self.assertNotIn('Roaming', text)

    def test_first_run_name_is_required_and_trimmed(self):
        api = Api()
        for name in ('', '  ', 'a'*81, 'Alex\n', None):
            with self.assertRaises(ValueError): api.finish_onboarding(name, ['en'], False)
        memory = Mock()
        with patch.object(api, '_memory', return_value=memory), patch('techvocab.seed'), patch.object(paths, 'save_settings') as save:
            api.finish_onboarding('  Alex  ', ['en'], False)
            self.assertEqual(save.call_args.args[0]['name'], 'Alex')
            memory.add_term.assert_any_call('Alex', 'you')


if __name__ == '__main__': unittest.main()
