import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('storage_manager', Path(__file__).parents[1] / 'core/storage_manager.py')
sm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sm)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir()
        self.external = Path(self.tmp.name) / 'external'
        self.external.mkdir()
        self.manager = sm.Manager(self.home)
        self.manager.config['data_root'] = str(self.external)

    def tearDown(self):
        self.tmp.cleanup()

    def entry(self, kind='cache'):
        return {'source': str(self.home / 'Library/Caches/test'), 'destination': str(self.external / 'test'), 'kind': kind, 'processes': []}

    def test_existing_destination_preserves_unique_local_files(self):
        e = self.entry()
        src, dst = Path(e['source']), Path(e['destination'])
        src.mkdir(parents=True); dst.mkdir()
        (src / 'new').write_text('new'); (dst / 'old').write_text('old')
        self.manager.migrate(e, busy=[])
        self.assertTrue(src.is_symlink())
        self.assertEqual((src / 'new').read_text(), 'new')
        self.assertEqual((src / 'old').read_text(), 'old')

    def test_conflict_keeps_both_copies(self):
        e = self.entry('persistent')
        src, dst = Path(e['source']), Path(e['destination'])
        src.mkdir(parents=True); dst.mkdir()
        (src / 'same').write_text('local'); (dst / 'same').write_text('external')
        with self.assertRaises(sm.StorageError):
            self.manager.migrate(e, busy=[])
        self.assertFalse(src.is_symlink())
        self.assertEqual((src / 'same').read_text(), 'local')
        self.assertEqual((dst / 'same').read_text(), 'external')

    def test_failed_link_preserves_source(self):
        e = self.entry(); src = Path(e['source']); src.mkdir(parents=True)
        (src / 'file').write_text('keep')
        with patch.object(self.manager, 'atomic_link', side_effect=OSError('link denied')):
            with self.assertRaises(OSError): self.manager.migrate(e, busy=[])
        self.assertEqual((src / 'file').read_text(), 'keep')

    def test_copy_failure_preserves_source(self):
        e = self.entry(); src = Path(e['source']); src.mkdir(parents=True)
        (src / 'file').write_text('keep')
        with patch.object(sm, 'copy_merge', side_effect=OSError('copy failed')):
            with self.assertRaises(OSError): self.manager.migrate(e, busy=[])
        self.assertEqual((src / 'file').read_text(), 'keep')

    def test_absent_cache_is_created_and_routed(self):
        e = self.entry(); self.manager.migrate(e, busy=[])
        self.assertTrue(Path(e['source']).is_symlink())
        self.assertTrue(Path(e['destination']).is_dir())

    def test_offline_routes_only_cache(self):
        cache, sdk = self.entry(), self.entry('persistent')
        sdk['source'] = str(self.home / 'sdk'); sdk['destination'] = str(self.external / 'sdk')
        self.manager.migrate(cache, busy=[]); self.manager.migrate(sdk, busy=[])
        self.manager.switch_entries([cache, sdk], online=False, busy=[])
        self.assertEqual(Path(cache['source']).resolve(), self.manager.fallback(cache['source']).resolve())
        self.assertEqual(os.readlink(sdk['source']), sdk['destination'])

    def test_busy_source_not_moved(self):
        e = self.entry(); e['processes'] = ['test-writer']
        with self.assertRaises(sm.StorageError): self.manager.migrate(e, busy=['test-writer'])
        self.assertFalse(Path(e['source']).is_symlink())

    def test_calendar_and_cli_do_not_block_other_app_caches(self):
        e = self.entry(); e['app_bundle'] = '/Applications/Notion.app'
        self.assertFalse(self.manager.is_busy(e, ['/Applications/Notion Calendar.app/Contents/MacOS/Notion Calendar']))
        self.assertTrue(self.manager.is_busy(e, ['/Applications/Notion.app/Contents/MacOS/Notion']))
        self.assertTrue(self.manager.is_busy(e, ['/Users/test/Applications/Notion.app/Contents/MacOS/Notion Helper (Renderer)']))
        e['app_bundle'] = '/Applications/Claude.app'
        self.assertFalse(self.manager.is_busy(e, ['claude']))
        self.assertTrue(self.manager.is_busy(e, ['/Applications/Claude.app/Contents/Helpers/chrome-native-host']))

    def test_chrome_mcp_is_not_a_browser_writer(self):
        e = self.entry(); e['processes'] = ['chrome']
        self.assertFalse(self.manager.is_busy(e, ['chrome-devtools-mcp']))
        self.assertTrue(self.manager.is_busy(e, ['chrome']))

    def test_writer_starting_during_copy_preserves_source(self):
        e = self.entry(); e['processes'] = ['test-writer']
        with patch.object(self.manager, 'processes', return_value=['test-writer']):
            with self.assertRaises(sm.StorageError): self.manager.migrate(e, busy=[])
        self.assertFalse(Path(e['source']).is_symlink())
        self.assertFalse(Path(e['destination']).exists())

    def test_quota_never_follows_links_or_deletes_persistent_data(self):
        e = self.entry(); sdk = self.entry('persistent'); sdk['source'] = str(self.home / 'sdk')
        cache = self.manager.fallback(e['source']); cache.mkdir(parents=True)
        persistent = self.home / 'precious'; persistent.mkdir(); (persistent / 'data').write_text('keep')
        (cache / 'outside').symlink_to(persistent, target_is_directory=True)
        (cache / 'cache').write_bytes(b'x' * 10000)
        self.manager.prune([e, sdk], budget=0, busy=[])
        self.assertEqual((persistent / 'data').read_text(), 'keep')
        self.assertTrue(cache.is_dir())
        self.assertFalse((cache / 'cache').exists())

    def test_invalid_external_destination_rejected(self):
        e = self.entry(); e['destination'] = str(self.home / 'important')
        with self.assertRaises(sm.StorageError): self.manager.validate_entry(e)

    def test_repeat_migration_keeps_data(self):
        e = self.entry(); self.manager.migrate(e, busy=[])
        (Path(e['source']) / 'test').write_text('keep')
        self.manager.migrate(e, busy=[])
        self.assertEqual((Path(e['source']) / 'test').read_text(), 'keep')

    def test_reconnect_flushes_fallback(self):
        e = self.entry(); self.manager.migrate(e, busy=[])
        self.manager.switch_entries([e], online=False, busy=[])
        (Path(e['source']) / 'offline').write_text('offline')
        self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual((Path(e['destination']) / 'offline').read_text(), 'offline')
        self.assertEqual(list(self.manager.fallback(e['source']).iterdir()), [])

    def test_mount_identity_does_not_require_nonexistent_mounted_field(self):
        info = {'MountPoint': '/Volumes/T9', 'VolumeUUID': sm.T9_UUID, 'FilesystemType': 'exfat'}
        with patch.object(self.manager, 'disk_info', return_value=info):
            self.assertTrue(self.manager.physical_online())
        info['VolumeUUID'] = 'another-device'
        with patch.object(self.manager, 'disk_info', return_value=info):
            self.assertFalse(self.manager.physical_online())

    def test_missing_t9_never_creates_image(self):
        self.manager.config['image'] = str(self.home / 'should-not-exist.sparsebundle')
        with patch.object(self.manager, 'physical_online', return_value=False):
            with self.assertRaises(sm.StorageError): self.manager.attach(create=True)
        self.assertFalse(Path(self.manager.config['image']).exists())

    def test_stray_mountpoint_data_is_set_aside_not_deleted(self):
        stray = self.external / 'DevCaches/.gradle/daemon/registry.bin.lock'
        stray.parent.mkdir(parents=True); stray.write_text('keep')
        self.manager.set_aside_stray_mountpoint_data()
        self.assertEqual(list(self.external.iterdir()), [])
        backups = list((self.manager.state / 'backups').iterdir())
        self.assertEqual((backups[0] / 'DevCaches/.gradle/daemon/registry.bin.lock').read_text(), 'keep')

    def test_gradle_pruning_preserves_configuration(self):
        e = self.entry(); e['prune_subdirs'] = ['caches']
        root = self.manager.fallback(e['source']); (root / 'caches').mkdir(parents=True)
        (root / 'gradle.properties').write_text('user-config')
        (root / 'caches/data').write_bytes(b'x' * 10000)
        self.manager.prune([e], budget=0, busy=[])
        self.assertEqual((root / 'gradle.properties').read_text(), 'user-config')
        self.assertFalse((root / 'caches/data').exists())

    def test_busy_cache_over_budget_is_reported_not_deleted(self):
        e = self.entry(); e['processes'] = ['test-writer']
        root = self.manager.fallback(e['source']); root.mkdir(parents=True)
        (root / 'data').write_bytes(b'x' * 10000)
        result = self.manager.prune([e], budget=0, busy=['test-writer'])
        self.assertTrue(result['over_budget'])
        self.assertTrue((root / 'data').exists())

    def test_fallback_symlink_is_never_cleaned(self):
        e = self.entry(); base = self.manager.fallback(e['source'])
        base.parent.mkdir(parents=True)
        victim = self.home / 'victim'; victim.mkdir(); (victim / 'data').write_text('keep')
        base.symlink_to(victim)
        with self.assertRaises(sm.StorageError): self.manager.prune([e], budget=0, busy=[])
        self.assertEqual((victim / 'data').read_text(), 'keep')

    def test_restore_retains_external_copy(self):
        e = self.entry(); self.manager.migrate(e, busy=[])
        (Path(e['source']) / 'data').write_text('keep')
        with patch.object(self.manager, 'processes', return_value=[]): self.manager.restore()
        self.assertFalse(Path(e['source']).is_symlink())
        self.assertEqual((Path(e['source']) / 'data').read_text(), 'keep')
        self.assertEqual((Path(e['destination']) / 'data').read_text(), 'keep')

    def test_lock_serializes_mutations(self):
        other = sm.Manager(self.home)
        with self.manager.locked():
            with self.assertRaises(BlockingIOError):
                with other.locked(): pass

    def test_logs_are_bounded_in_place(self):
        path = self.home / 'Library/Logs/com.ssd-migration.switch-links.log'
        path.parent.mkdir(parents=True); path.write_bytes(b'x' * 20000)
        self.manager.config['log_max_bytes'] = 4096
        inode = path.stat().st_ino
        self.manager.rotate_logs()
        self.assertLessEqual(path.stat().st_size, 4096)
        self.assertEqual(path.stat().st_ino, inode)

    def test_reconnect_prefers_current_disposable_cache(self):
        e = self.entry(); self.manager.migrate(e, busy=[])
        (Path(e['destination']) / 'cache').write_text('old')
        self.manager.switch_entries([e], online=False, busy=[])
        (Path(e['source']) / 'cache').write_text('new')
        results = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(results[0]['state'], 'external')
        self.assertEqual((Path(e['destination']) / 'cache').read_text(), 'new')

    def test_gradle_configuration_conflict_remains_intact(self):
        e = self.entry(); e['prune_subdirs'] = ['caches']
        self.manager.migrate(e, busy=[])
        (Path(e['destination']) / 'gradle.properties').write_text('external-config')
        self.manager.switch_entries([e], online=False, busy=[])
        (Path(e['source']) / 'gradle.properties').write_text('local-config')
        results = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(results[0]['state'], 'blocked')
        self.assertEqual((Path(e['source']) / 'gradle.properties').read_text(), 'local-config')
        self.assertEqual((Path(e['destination']) / 'gradle.properties').read_text(), 'external-config')

    def test_reconnect_flushes_leftover_fallback_even_when_link_is_external(self):
        e = self.entry(); self.manager.migrate(e, busy=[])
        root = self.manager.fallback(e['source']); root.mkdir(parents=True)
        (root / 'leftover').write_text('keep')
        self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual((Path(e['destination']) / 'leftover').read_text(), 'keep')
        self.assertEqual(list(root.iterdir()), [])

    def test_gradle_configuration_is_available_offline(self):
        e = self.entry(); e['source'] = str(self.home / '.gradle'); e['prune_subdirs'] = ['caches']
        self.manager.migrate(e, busy=[])
        (Path(e['destination']) / 'gradle.properties').write_text('private-repository-config')
        self.manager.switch_entries([e], online=True, busy=[])
        self.manager.switch_entries([e], online=False, busy=[])
        self.assertEqual((Path(e['source']) / 'gradle.properties').read_text(), 'private-repository-config')

    def test_updated_external_config_refreshes_unmodified_snapshot(self):
        e = self.entry(); e['source'] = str(self.home / '.m2')
        self.manager.migrate(e, busy=[])
        file = Path(e['destination']) / 'settings.xml'; file.write_text('old')
        self.manager.snapshot_configuration(e); file.write_text('new')
        self.manager.snapshot_configuration(e)
        self.assertEqual((self.manager.fallback(e['source']) / 'settings.xml').read_text(), 'new')

    def test_unchanged_configuration_does_not_trigger_recurring_migration(self):
        e = self.entry(); e['source'] = str(self.home / '.gradle'); e['prune_subdirs'] = ['caches']
        self.manager.migrate(e, busy=[])
        (Path(e['destination']) / 'gradle.properties').write_text('config')
        self.manager.switch_entries([e], online=True, busy=[])
        inode = Path(e['destination']).stat().st_ino
        with patch.object(self.manager, 'online', return_value=True), patch.object(self.manager, 'processes', return_value=[]):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'external')
        self.assertEqual(Path(e['destination']).stat().st_ino, inode)

    def gradle_fallback(self):
        e = self.entry()
        e['source'] = str(self.home / '.gradle')
        e['prune_subdirs'] = ['caches', 'wrapper/dists', 'daemon']
        self.manager.migrate(e, busy=[])
        self.manager.switch_entries([e], online=False, busy=[])
        base = self.manager.fallback(e['source'])
        (base / 'caches').mkdir()
        (base / 'caches/local').write_text('regenerable')
        return e, base, Path(e['destination'])

    def test_gradle_reconnect_discards_local_cache_without_copying_external_cache(self):
        e, base, dst = self.gradle_fallback()
        (dst / 'caches').mkdir(); (dst / 'caches/external').write_text('reuse')
        (base / 'gradle.properties').write_text('configuration')
        (base / 'custom-data').write_text('preserve unknown files')
        with patch.object(self.manager, 'online', return_value=True), patch.object(self.manager, 'processes', return_value=[]), patch.object(self.manager, 'migrate', side_effect=AssertionError('No full migration')):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'external')
        self.assertEqual((dst / 'caches/external').read_text(), 'reuse')
        self.assertFalse((dst / 'caches/local').exists())
        self.assertFalse((base / 'caches/local').exists())
        self.assertEqual((dst / 'custom-data').read_text(), 'preserve unknown files')
        self.assertEqual((base / 'gradle.properties').read_text(), 'configuration')

    def test_gradle_reconnect_conflict_keeps_cache_and_local_link(self):
        e, base, dst = self.gradle_fallback()
        (base / 'gradle.properties').write_text('local')
        (dst / 'gradle.properties').write_text('external')
        with patch.object(self.manager, 'online', return_value=True), patch.object(self.manager, 'processes', return_value=[]):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'blocked')
        self.assertEqual(Path(e['source']).resolve(), base.resolve())
        self.assertTrue((base / 'caches/local').exists())

    def test_gradle_reconnect_checks_device_and_preserves_cache_on_link_failure(self):
        e, base, dst = self.gradle_fallback()
        with patch.object(self.manager, 'online', return_value=False):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'blocked')
        self.assertTrue((base / 'caches/local').exists())
        with patch.object(self.manager, 'online', return_value=True), patch.object(self.manager, 'processes', return_value=[]), patch.object(self.manager, 'atomic_link', side_effect=OSError('denied')):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'blocked')
        self.assertTrue((base / 'caches/local').exists())

    def test_gradle_reconnect_rejects_cache_symlink_and_new_writer(self):
        e, base, dst = self.gradle_fallback()
        victim = self.home / 'valuable'; victim.mkdir(); (victim / 'file').write_text('keep')
        (base / 'daemon').symlink_to(victim, target_is_directory=True)
        with patch.object(self.manager, 'online', return_value=True), patch.object(self.manager, 'processes', return_value=[]):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'blocked')
        self.assertEqual((victim / 'file').read_text(), 'keep')
        (base / 'daemon').unlink()
        e['processes'] = ['java']
        with patch.object(self.manager, 'online', return_value=True), patch.object(self.manager, 'processes', return_value=['java']):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'blocked')
        self.assertTrue((base / 'caches/local').exists())

    def test_gradle_reconnect_preserves_newer_external_config_and_wrapper_settings(self):
        e, base, dst = self.gradle_fallback()
        (dst / 'gradle.properties').write_text('old')
        self.manager.snapshot_configuration(e)
        (dst / 'gradle.properties').write_text('new')
        (base / 'wrapper/dists').mkdir(parents=True)
        (base / 'wrapper/dists/download.zip').write_text('downloadable')
        (base / 'wrapper/private-settings').write_text('keep')
        with patch.object(self.manager, 'online', return_value=True), patch.object(self.manager, 'processes', return_value=[]):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'external')
        self.assertEqual((base / 'gradle.properties').read_text(), 'new')
        self.assertEqual((dst / 'wrapper/private-settings').read_text(), 'keep')
        self.assertFalse((base / 'wrapper/dists/download.zip').exists())
        self.assertFalse((dst / 'wrapper/dists/download.zip').exists())

    def test_gradle_reconnect_disconnect_before_link_keeps_cache(self):
        e, base, dst = self.gradle_fallback()
        with patch.object(self.manager, 'online', side_effect=[True, False]), patch.object(self.manager, 'processes', return_value=[]):
            result = self.manager.switch_entries([e], online=True, busy=[])
        self.assertEqual(result[0]['state'], 'blocked')
        self.assertEqual(Path(e['source']).resolve(), base.resolve())
        self.assertTrue((base / 'caches/local').exists())


if __name__ == '__main__': unittest.main()
