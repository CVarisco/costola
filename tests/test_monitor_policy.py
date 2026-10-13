from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.app_manager import AppManager
from core.engine_api import dispatch


class MonitorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.manager = AppManager(self.home)

    def register(self, identity):
        with self.manager.locked():
            entry = next(e for e in self.manager.specs() if e['id'] == identity)
            target = Path(entry['destination'])
            target.mkdir(parents=True)
            source = Path(entry['source'])
            source.parent.mkdir(parents=True, exist_ok=True)
            source.symlink_to(target)
            self.manager.entries = [entry]
            self.manager.document['selected'] = [identity]
            self.manager.save()
        return entry

    def test_offline_cache_uses_costola_fallback_only(self):
        entry = self.register('npm')
        with self.manager.locked(), patch.object(self.manager, 'processes', return_value=[]):
            result = self.manager.switch_entries(self.manager.entries, False, [])
        self.assertEqual(result[0]['state'], 'local-fallback')
        self.assertEqual(Path(entry['source']).resolve(), self.manager.store.fallback / '.npm')
        self.assertFalse((self.home / '.ssd-migration-fallback').exists())

    def test_monitor_refuses_mutation_while_another_operation_holds_lock(self):
        with self.manager.locked():
            self.manager.document['automation_enabled'] = True
            self.manager.save()
            result = dispatch({'command': 'monitor'}, home=self.home)
        self.assertEqual(result['state'], 'busy')

    def test_disabled_automation_does_not_attach_or_migrate(self):
        with patch.object(AppManager, 'attach') as attach, patch.object(AppManager, 'migrate') as migrate:
            result = dispatch({'command': 'monitor'}, home=self.home)
        self.assertEqual(result['state'], 'disabled')
        attach.assert_not_called()
        migrate.assert_not_called()
        self.assertFalse(self.manager.store.path.exists())

    def test_interrupted_operation_prevents_background_cleanup(self):
        self.register('npm')
        with self.manager.locked():
            self.manager.document['automation_enabled'] = True
            self.manager.document['operations']['unfinished'] = {'phase': 'copying'}
            self.manager.save()
            with patch.object(self.manager, 'prune') as prune:
                result = self.manager.monitor()
            prune.assert_not_called()
        self.assertEqual(result['state'], 'recovery-required')

    def test_pruning_preserves_active_cache_and_persistent_folders(self):
        entry = self.register('npm')
        cache = self.manager.fallback(entry['source'])
        cache.mkdir(parents=True)
        (cache / 'payload').write_bytes(b'x' * 4096)
        with patch.object(self.manager, 'is_busy', return_value=True):
            result = self.manager.prune([entry], 0, [])
        self.assertTrue(result['over_budget'])
        self.assertTrue((cache / 'payload').exists())
        entry['kind'] = 'persistent'
        self.manager.prune([entry], 0, [])
        self.assertTrue((cache / 'payload').exists())
