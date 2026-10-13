"""An actual frozen-worker sweep, isolated from the user's home and disks."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from core.app_manager import AppManager


class BackgroundLifecycleTests(unittest.TestCase):
    def test_packaged_worker_routes_and_prunes_only_authorized_fixture_cache(self):
        worker = Path(os.environ['COSTOLA_APP']) / 'Contents/Helpers/CostolaWorker.app/Contents/MacOS/CostolaWorker'
        with tempfile.TemporaryDirectory(prefix='Costola monitor fixture ') as directory:
            home = Path(directory).resolve()
            manager = AppManager(home)
            with manager.locked():
                entry = next(e for e in manager.specs() if e['id'] == 'npm')
                entry['processes'] = []  # The isolated fixture is never used by the user's running npm.
                source = Path(entry['source'])
                source.symlink_to(entry['destination'])
                fallback = manager.fallback(source)
                fallback.mkdir(parents=True)
                (fallback / 'disposable').write_bytes(b'x' * 4096)
                protected = home / 'Projects/keep.txt'
                protected.parent.mkdir()
                protected.write_text('unique personal file')
                manager.entries = [entry]
                manager.document['selected'] = ['npm']
                manager.document['automation_enabled'] = True
                manager.document['settings']['cache_budget_bytes'] = 0
                manager.save()
            request = json.dumps({'protocol_version': 1, 'request_id': 'sweep', 'command': 'monitor'})
            result = subprocess.run([str(worker)], input=request, capture_output=True, text=True,
                                    env={'HOME': str(home), 'PATH': '/usr/bin:/bin'}, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)['data']
            self.assertEqual(payload['state'], 'checked')
            self.assertEqual(source.resolve(), fallback)
            self.assertFalse((fallback / 'disposable').exists())
            self.assertEqual(protected.read_text(), 'unique personal file')
            self.assertFalse((home / '.ssd-migration').exists())
            receipt = json.loads((manager.state / 'monitor-state.json').read_text())
            self.assertGreater(receipt['checked_at'], 0)
            self.assertGreater(receipt['cleanup']['removed_bytes'], 0)
