"""Run with COSTOLA_APP pointing to the final .app; missing assets fail the gate."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PackagedWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Path(os.environ['COSTOLA_APP']).resolve()
        if not cls.app.is_dir():
            raise FileNotFoundError(cls.app)

    def test_relocated_launcher_uses_frozen_worker_without_external_python(self):
        with tempfile.TemporaryDirectory(prefix='Costola package ') as directory:
            root = Path(directory)
            app = root / 'App with spaces' / 'Costola.app'
            shutil.copytree(self.app, app, symlinks=True)
            home = root / 'home'
            home.mkdir()
            launcher = app / 'Contents/MacOS/CostolaAgent'
            result = subprocess.run(
                [str(launcher)], cwd=root, capture_output=True, text=True,
                env={'HOME': str(home), 'PATH': ''}, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            self.assertTrue(response['success'])
            self.assertEqual(response['data']['product'], 'Costola')
            self.assertTrue(response['data']['frozen'])
            self.assertEqual(list(home.iterdir()), [])

    def test_missing_worker_fails_instead_of_reporting_success(self):
        with tempfile.TemporaryDirectory(prefix='Costola missing worker ') as directory:
            app = Path(directory) / 'Costola.app'
            (app / 'Contents/MacOS').mkdir(parents=True)
            launcher = app / 'Contents/MacOS/CostolaAgent'
            shutil.copy2(self.app / 'Contents/MacOS/CostolaAgent', launcher)
            result = subprocess.run([str(launcher)], capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
            self.assertIn('worker', result.stderr.lower())

    def test_modified_worker_resources_fail_signature_validation(self):
        with tempfile.TemporaryDirectory(prefix='Costola invalid signature ') as directory:
            app = Path(directory) / 'Costola.app'
            shutil.copytree(self.app, app, symlinks=True)
            archive = app / 'Contents/Helpers/CostolaWorker.app/Contents/Resources/base_library.zip'
            with archive.open('ab') as stream:
                stream.write(b'changed')
            result = subprocess.run(
                [str(app / 'Contents/MacOS/CostolaAgent')],
                capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
            self.assertIn('signature', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
