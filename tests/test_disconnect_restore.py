from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.app_manager import AppManager
from core.storage_manager import StorageError


class DisconnectRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.manager = AppManager(self.home)

    def configure_npm(self):
        entry = next(e for e in self.manager.specs() if e['id'] == 'npm')
        self.manager.entries = [entry]
        self.manager.document['selected'] = ['npm']
        self.manager.configure()
        return entry

    def test_restore_configuration_preserves_subsequent_user_changes(self):
        path = self.home / '.npmrc'
        path.write_text('cache=/original\nregistry=https://example.invalid\n')
        with self.manager.locked():
            self.configure_npm()
            path.write_text(path.read_text() + 'always-auth=true\n')
            self.manager.restore_configuration('npm')
        self.assertEqual(path.read_text(), 'registry=https://example.invalid\nalways-auth=true\ncache=/original\n')

    def test_user_replaced_managed_setting_is_not_overwritten(self):
        path = self.home / '.npmrc'
        path.write_text('cache=/original\n')
        with self.manager.locked():
            self.configure_npm()
            path.write_text('cache=/user-chosen\n')
            self.manager.restore_configuration('npm')
        self.assertEqual(path.read_text(), 'cache=/user-chosen\n')

    def test_active_writer_prevents_detach(self):
        with self.manager.locked(), patch.object(self.manager, 'online', return_value=True), \
                patch.object(self.manager, 'check_writers', side_effect=StorageError('Active writer')), \
                patch('core.app_manager.run') as run:
            self.configure_npm()
            with self.assertRaises(StorageError):
                self.manager.disconnect()
            run.assert_not_called()

    def test_disconnect_does_not_use_force_and_next_monitor_does_not_remount(self):
        with self.manager.locked(), patch.object(self.manager, 'online', return_value=True), \
                patch.object(self.manager, 'physical_online', return_value=True), \
                patch.object(self.manager, 'processes', return_value=[]), \
                patch('core.app_manager.run') as run:
            self.manager.document['automation_enabled'] = True
            self.manager.disconnect()
            run.assert_called_once_with(['/usr/bin/hdiutil', 'detach', str(self.manager.root)])
            self.assertTrue(self.manager.config['manual_detached'])
            with patch.object(self.manager, 'online', return_value=False), patch.object(self.manager, 'attach') as attach:
                self.manager.monitor()
            attach.assert_not_called()

    def test_partial_restore_keeps_automation_and_reports_both_results(self):
        with self.manager.locked():
            self.manager.entries = [{'id': 'first'}, {'id': 'second'}]
            self.manager.document['automation_enabled'] = True
            def restore_one(entry, dry_run):
                if entry['id'] == 'first':
                    raise StorageError('Not enough space')
                self.manager.entries = [e for e in self.manager.entries if e['id'] != 'second']
                return {'id': 'second', 'state': 'restored-external-copy-retained'}
            with patch.object(self.manager, '_restore_entry', side_effect=restore_one):
                result = self.manager.restore()
            self.assertEqual([r['state'] for r in result], ['blocked', 'restored-external-copy-retained'])
            self.assertTrue(self.manager.document['automation_enabled'])
            self.assertEqual([e['id'] for e in self.manager.entries], ['first'])
