import json
from pathlib import Path
import tempfile
import unittest

from core.state import StateStore, StateError
from core.app_manager import AppManager


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.store = StateStore(self.home)

    def test_read_does_not_initialize_state(self):
        self.assertEqual(self.store.read()['selected'], [])
        self.assertFalse(self.store.root.exists())

    def test_selection_queues_only_authorized_entries(self):
        self.store.select(['npm'], known_ids={'npm', 'yarn'}, revision=0)
        state = StateStore(self.home).read()
        self.assertEqual(state['selected'], ['npm'])
        self.assertEqual(state['pending'], ['npm'])
        self.assertEqual(state['revision'], 1)

    def test_deselect_pending_cancels_it_but_migrated_requires_restore(self):
        self.store.select(['npm', 'yarn'], known_ids={'npm', 'yarn'}, revision=0)
        self.store.change(1, lambda state: state['entries'].update({'npm': {'source': 'fixture'}}))
        with self.assertRaises(StateError):
            self.store.select([], known_ids={'npm', 'yarn'}, revision=2)
        self.store.select(['npm'], known_ids={'npm', 'yarn'}, revision=2)
        self.assertEqual(self.store.read()['pending'], [])
        self.assertIn('npm', self.store.read()['entries'])

    def test_stale_selection_cannot_overwrite_new_authorization(self):
        self.store.select(['npm'], known_ids={'npm'}, revision=0)
        with self.assertRaises(StateError):
            self.store.select([], known_ids={'npm'}, revision=0)
        self.assertEqual(self.store.read()['selected'], ['npm'])

    def test_future_schema_is_rejected_without_rewriting(self):
        self.store.root.mkdir(parents=True)
        self.store.path.write_text(json.dumps({'version': 99}))
        before = self.store.path.read_bytes()
        with self.assertRaises(StateError):
            self.store.select([], known_ids=set(), revision=0)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertFalse((self.store.root / 'lock').exists())

    def test_legacy_configuration_is_not_loaded_or_changed(self):
        legacy = self.home / '.ssd-migration'
        legacy.mkdir()
        config = legacy / 'config.json'
        config.write_text('{"physical_uuid":"personal"}')
        self.assertIsNone(self.store.read()['device'])
        self.store.select([], known_ids=set(), revision=0)
        self.assertEqual(config.read_text(), '{"physical_uuid":"personal"}')

    def test_only_migrated_selected_npm_configuration_is_changed(self):
        (self.home / '.npm').mkdir()
        (self.home / '.npmrc').write_text('registry=https://example.test\nstore-dir=keep-me\n')
        (self.home / '.yarnrc').write_text('cache-folder original\n')
        (self.home / '.zshrc').write_text('export ORIGINAL=yes\n')
        manager = AppManager(self.home)
        manager.select(['npm'], 0)
        with manager.locked():
            manager.entries = [next(entry for entry in manager.specs() if entry['id'] == 'npm')]
            manager.configure()
        self.assertIn('store-dir=keep-me', (self.home / '.npmrc').read_text())
        self.assertIn('cache=' + str(self.home.resolve() / '.npm'), (self.home / '.npmrc').read_text())
        self.assertEqual((self.home / '.yarnrc').read_text(), 'cache-folder original\n')
        self.assertEqual((self.home / '.zshrc').read_text(), 'export ORIGINAL=yes\n')

    def test_personal_folder_configuration_leaves_tool_files_untouched(self):
        folder = self.home / 'Work'
        folder.mkdir()
        manager = AppManager(self.home)
        entry = manager.add_custom(folder, 0)
        manager.select([entry['id']], 1)
        with manager.locked():
            manager.entries = [next(item for item in manager.specs() if item['id'] == entry['id'])]
            manager.configure()
        for filename in ('.npmrc', '.yarnrc', '.zshrc'):
            self.assertFalse((self.home / filename).exists())

    def test_legacy_managed_link_blocks_new_setup(self):
        legacy = self.home / '.ssd-migration'
        legacy.mkdir()
        link = self.home / '.npm'
        link.symlink_to(self.home / 'missing-old-destination')
        (legacy / 'registry.json').write_text(json.dumps({'entries': [{'source': str(link)}]}))
        self.assertTrue(AppManager(self.home).legacy_conflicts())
