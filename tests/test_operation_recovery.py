from pathlib import Path
import os
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

    def test_unchanged_retained_fallback_does_not_overwrite_newer_external_cache(self):
        with self.manager.locked():
            self.manager.migrate(self.entry, [])
            self.manager.switch_entries(self.manager.entries, False, [])
            fallback = self.manager.fallback(self.entry['source'])
            (fallback / 'offline').write_text('offline version')
            self.manager.migrate(self.entry, [], local_override=fallback)
            external = Path(self.entry['destination']) / 'offline'
            external.write_text('new external version')
            self.assertFalse(self.manager.fallback_needs_flush(self.entry))
            self.manager.switch_entries(self.manager.entries, True, [])
            self.assertEqual(external.read_text(), 'new external version')

    def test_unique_file_added_to_backup_is_never_deleted(self):
        original = self.manager._phase
        def late_writer(operation, phase):
            original(operation, phase)
            if phase == 'linked':
                backup = Path(operation['backup'])
                metadata = backup.stat()
                (backup / 'late-unique').write_text('new data')
                os.utime(backup, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        with self.manager.locked(), patch.object(self.manager, '_phase', side_effect=late_writer):
            with self.assertRaises(CopyError):
                self.manager.migrate(self.entry, [])
        operation = next(iter(self.manager.store.read()['operations'].values()))
        self.assertEqual(operation['phase'], 'recovery-required')
        self.assertEqual(Path(operation['backup']).joinpath('late-unique').read_text(), 'new data')

    def test_configuration_failure_is_recoverable_and_retains_backup(self):
        with self.manager.locked(), patch.object(self.manager, 'configure', side_effect=OSError('Config permission denied')):
            with self.assertRaises(OSError):
                self.manager.migrate(self.entry, [])
        identity, operation = next(iter(self.manager.store.read()['operations'].items()))
        self.assertEqual(operation['phase'], 'recovery-required')
        self.assertTrue(Path(operation['backup']).joinpath('unique').exists())
        with self.manager.locked():
            self.manager.recover(identity)
        self.assertEqual(self.manager.store.read()['operations'][identity]['phase'], 'completed')
        self.assertIn('cache=', (self.home / '.npmrc').read_text())

    def test_restore_reconciles_offline_files_before_unregistering(self):
        with self.manager.locked():
            self.manager.migrate(self.entry, [])
            self.manager.switch_entries(self.manager.entries, False, [])
            (self.manager.fallback(self.entry['source']) / 'offline').write_text('offline data')
            results = self.manager.restore()
        self.assertEqual(results[0]['state'], 'restored-external-copy-retained')
        self.assertEqual((self.home / '.npm/unique').read_text(), 'keep')
        self.assertEqual((self.home / '.npm/offline').read_text(), 'offline data')

    def test_restore_offline_does_not_unregister_incomplete_local_data(self):
        with self.manager.locked():
            self.manager.migrate(self.entry, [])
            self.manager.switch_entries(self.manager.entries, False, [])
            with patch.object(self.manager, 'online', return_value=False):
                results = self.manager.restore()
        self.assertEqual(results[0]['state'], 'blocked')
        self.assertIn('npm', self.manager.store.read()['entries'])
        self.assertTrue((self.home / '.npm').is_symlink())

    def test_new_process_recovers_interrupted_restore_without_losing_either_copy(self):
        class Interrupted(BaseException):
            pass
        for phase in ('copying', 'verified', 'publishing', 'published', 'completed'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                home = Path(directory).resolve()
                (home / '.npm').mkdir()
                (home / '.npm/unique').write_text('retained')
                manager = AppManager(home)
                manager.select(['npm'], 0)
                manager.root.mkdir(parents=True)
                entry = next(item for item in manager.specs() if item['id'] == 'npm')
                with manager.locked(), patch.object(manager, 'online', return_value=True), \
                        patch.object(manager, 'check_writers'), patch.object(manager, 'check_space'):
                    manager.migrate(entry, [])
                    original = manager._phase
                    def interrupt(operation, next_phase):
                        original(operation, next_phase)
                        if next_phase == phase:
                            raise Interrupted()
                    with patch.object(manager, '_phase', side_effect=interrupt):
                        with self.assertRaises(Interrupted):
                            manager.restore()
                fresh = AppManager(home)
                identity = next(key for key, op in fresh.document['operations'].items() if op['kind'] == 'restore')
                with fresh.locked(), patch.object(fresh, 'online', return_value=True), patch.object(fresh, 'check_writers'):
                    fresh.recover(identity)
                self.assertEqual((home / '.npm/unique').read_text(), 'retained')
                self.assertEqual(Path(entry['destination']).joinpath('unique').read_text(), 'retained')
