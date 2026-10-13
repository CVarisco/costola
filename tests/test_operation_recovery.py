from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.app_manager import AppManager
from core.storage_manager import StorageError
from core.macos_copy import copy_tree, CopyError


class OperationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / 'home'
        self.home.mkdir()
        (self.home / '.npm').mkdir()
        (self.home / '.npm/unique').write_text('keep')
        self.manager = AppManager(self.home)
        self.manager.select(['npm'], 0)
        self.manager.root.mkdir(parents=True)
        self.entry = next(entry for entry in self.manager.specs() if entry['id'] == 'npm')
        self.addCleanup(patch.stopall)
        patch.object(self.manager, 'online', return_value=True).start()
        patch.object(self.manager, 'processes', return_value=[]).start()
        patch.object(self.manager, 'check_writers', return_value=None).start()
        patch.object(self.manager, 'check_space', return_value=None).start()

    def test_verified_migration_replaces_source_and_completes_journal(self):
        with self.manager.locked():
            self.manager.migrate(self.entry, [])
        self.assertTrue((self.home / '.npm').is_symlink())
        self.assertEqual((self.home / '.npm/unique').read_text(), 'keep')
        state = self.manager.store.read()
        self.assertIn('npm', state['entries'])
        self.assertEqual(state['pending'], [])
        self.assertEqual([op['phase'] for op in state['operations'].values()], ['completed'])

    def test_failure_after_source_rename_recovers_local_original(self):
        with self.manager.locked():
            with patch.object(self.manager, 'atomic_link', side_effect=StorageError('fixture link failure')):
                with self.assertRaises(StorageError):
                    self.manager.migrate(self.entry, [])
        state = self.manager.store.read()
        operation_id, operation = next(iter(state['operations'].items()))
        self.assertEqual(Path(operation['backup']).joinpath('unique').read_text(), 'keep')
        with self.manager.locked():
            self.manager.recover(operation_id)
        self.assertFalse((self.home / '.npm').is_symlink())
        self.assertEqual((self.home / '.npm/unique').read_text(), 'keep')
        self.assertEqual(Path(self.entry['destination']).joinpath('unique').read_text(), 'keep')

    def test_disconnect_before_cleanup_retains_backup(self):
        calls = 0
        def online():
            nonlocal calls
            calls += 1
            return calls < 3
        with self.manager.locked(), patch.object(self.manager, 'online', side_effect=online):
            with self.assertRaises(StorageError):
                self.manager.migrate(self.entry, [])
        operation = next(iter(self.manager.store.read()['operations'].values()))
        self.assertEqual(Path(operation['backup']).joinpath('unique').read_text(), 'keep')

    def test_restore_keeps_external_copy(self):
        with self.manager.locked():
            self.manager.migrate(self.entry, [])
            self.manager.restore()
        self.assertFalse((self.home / '.npm').is_symlink())
        self.assertEqual((self.home / '.npm/unique').read_text(), 'keep')
        self.assertEqual(Path(self.entry['destination']).joinpath('unique').read_text(), 'keep')
        self.assertEqual(self.manager.store.read()['entries'], {})

    def test_changed_source_is_preserved_and_never_published_as_success(self):
        def changed(source, target, **kwargs):
            expected = copy_tree(source, target, **kwargs)
            (source / 'unique').write_text('new writes')
            return expected
        with self.manager.locked(), patch('core.app_manager.copy_tree', side_effect=changed):
            with self.assertRaises(CopyError):
                self.manager.migrate(self.entry, [])
        self.assertFalse((self.home / '.npm').is_symlink())
        self.assertEqual((self.home / '.npm/unique').read_text(), 'new writes')
        self.assertEqual(next(iter(self.manager.store.read()['operations'].values()))['phase'], 'recovery-required')

    def test_new_process_recovers_each_durable_phase_without_losing_unique_data(self):
        class Interrupted(BaseException):
            pass
        for phase in ('copying', 'verified', 'publishing', 'published', 'linked', 'completed'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                home = Path(directory).resolve()
                (home / '.npm').mkdir()
                (home / '.npm/unique').write_text('retained')
                manager = AppManager(home)
                manager.select(['npm'], 0)
                manager.root.mkdir(parents=True)
                entry = next(item for item in manager.specs() if item['id'] == 'npm')
                original = manager._phase
                def interrupt(operation, next_phase):
                    original(operation, next_phase)
                    if next_phase == phase:
                        raise Interrupted()
                with manager.locked(), patch.object(manager, 'online', return_value=True), \
                        patch.object(manager, 'check_writers'), patch.object(manager, 'check_space'), \
                        patch.object(manager, '_phase', side_effect=interrupt):
                    with self.assertRaises(Interrupted):
                        manager.migrate(entry, [])
                fresh = AppManager(home)
                operation_id = next(iter(fresh.document['operations']))
                with fresh.locked(), patch.object(fresh, 'online', return_value=True), patch.object(fresh, 'check_writers'):
                    fresh.recover(operation_id)
                self.assertEqual((home / '.npm/unique').read_text(), 'retained')
