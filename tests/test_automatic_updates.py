import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import control
import paths
import updates
from flow import Flow
from ui import Api


class AutomaticUpdates(unittest.TestCase):
    def scheduler(self, phase='idle'):
        manager = Mock()
        manager.status.return_value = {'phase': phase}
        reserve, close = Mock(return_value=True), Mock()
        with patch('updates.time.monotonic', return_value=100):
            scheduler = updates.Automatic(manager, close, reserve)
        return scheduler, manager, reserve, close

    def test_checks_without_opening_settings_and_retries_offline(self):
        scheduler, manager, _, _ = self.scheduler()
        scheduler.tick(True, True, 129); manager.check.assert_not_called()
        scheduler.tick(True, True, 130); manager.check.assert_called_once()
        manager.status.return_value = {'phase': 'error'}
        scheduler.tick(True, True, 131)
        scheduler.tick(True, True, 1030); self.assertEqual(manager.check.call_count, 1)
        scheduler.tick(True, True, 1031); self.assertEqual(manager.check.call_count, 2)

    def test_recording_defers_update_until_sixty_seconds_of_idle(self):
        scheduler, manager, reserve, close = self.scheduler('available')
        scheduler.tick(True, False, 200)
        scheduler.tick(True, True, 259); manager.apply.assert_not_called()
        scheduler.tick(True, True, 260); manager.apply.assert_called_once()
        self.assertIs(manager.apply.call_args.args[0], close)
        self.assertTrue(manager.apply.call_args.kwargs['can_install']())
        reserve.assert_called_once_with(True)

    def test_disabled_automatic_updates_do_not_check_or_install(self):
        for phase in ('idle', 'available'):
            scheduler, manager, _, _ = self.scheduler(phase)
            scheduler.tick(False, True, 1000)
            manager.check.assert_not_called(); manager.apply.assert_not_called()

    def test_post_download_reservation_refuses_handoff_when_user_resumes(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(paths, 'DATA', Path(folder)):
            manager = updates.Manager(); manager.asset = {'version': '9.0.0'}
            manager._set(phase='available')
            finished = threading.Event()
            original = manager._set
            def state(**kw):
                original(**kw)
                if kw.get('phase') == 'available': finished.set()
            manager._set = state
            with patch('control.state', return_value={}), patch('updates.token', return_value=''), patch('updates.download', return_value=Path(folder)/'FlowSetup.exe'), patch('updates.install') as install:
                close = Mock()
                manager.apply(close, can_install=lambda: False)
                self.assertTrue(finished.wait(2))
                install.assert_not_called(); close.assert_not_called()
                self.assertEqual(manager.status()['phase'], 'available')

    def test_settings_route_to_tray_updater_instead_of_starting_another_job(self):
        state = {'alive': True, 'updates': {'phase': 'available', 'current': updates.APP_VERSION}}
        with patch('control.state', return_value=state), patch('control.send') as send, patch('updates.Manager') as manager:
            api = Api()
            self.assertEqual(api.update_status()['phase'], 'available')
            api.check_updates(); api.install_update()
            self.assertEqual([c.args[0] for c in send.call_args_list], ['update_check', 'update_install'])
            manager.assert_not_called()

    def test_open_window_closes_for_background_install(self):
        api = Api(); api._window = Mock()
        with patch('control.state', return_value={'updates': {'phase': 'installing'}}):
            api.update_status(); api.update_status()
        api._window.destroy.assert_called_once()

    def test_install_reservation_blocks_new_microphone_capture(self):
        flow = Flow.__new__(Flow); flow.updating = True
        with patch('sounddevice.InputStream') as capture:
            flow.start('ptt')
        capture.assert_not_called()


if __name__ == '__main__': unittest.main()
