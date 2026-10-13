"""Live hdiutil integration on disposable images, never on a personal SSD."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from core.app_manager import AppManager


class StorageRoundTripTests(unittest.TestCase):
    def test_apfs_and_exfat_backing_images_round_trip(self):
        if os.environ.get('COSTOLA_STORAGE_INTEGRATION') != '1':
            self.skipTest('Set COSTOLA_STORAGE_INTEGRATION=1 to create disposable disk images.')
        for filesystem in ('APFS', 'ExFAT'):
            with self.subTest(filesystem=filesystem):
                self.round_trip(filesystem)

    def round_trip(self, filesystem):
        root = Path(tempfile.mkdtemp(prefix='Costola disk fixture ')).resolve()
        home = root / 'home'
        home.mkdir()
        backing = root / 'backing.sparsebundle'
        mount = root / 'external'
        mount.mkdir()
        manager = AppManager(home)
        mounted = False
        try:
            subprocess.run(['hdiutil', 'create', '-size', '4g', '-type', 'SPARSEBUNDLE', '-fs', filesystem,
                            '-volname', 'Fixture', str(backing)], check=True)
            subprocess.run(['hdiutil', 'attach', '-nobrowse', '-mountpoint', str(mount), str(backing)], check=True, capture_output=True)
            mounted = True
            personal = home / 'Personal'
            personal.mkdir()
            (personal / 'unique.txt').write_text('retain unique bytes')
            manager.choose_device(mount, 0)
            entry = manager.add_custom(personal, manager.document['revision'])
            manager.select([entry['id']], manager.document['revision'])
            with manager.locked():
                manager.attach(create=True)
                self.assertTrue(manager.online())
                specification = next(e for e in manager.specs() if e['id'] == entry['id'])
                manager.migrate(specification, manager.processes())
                self.assertTrue(personal.is_symlink())
                self.assertEqual((personal / 'unique.txt').read_text(), 'retain unique bytes')
                manager.disconnect()
                self.assertFalse(personal.exists())
                manager.attach()
                self.assertEqual((personal / 'unique.txt').read_text(), 'retain unique bytes')
                result = manager.restore()
                self.assertEqual(result[0]['state'], 'restored-external-copy-retained')
                self.assertFalse(personal.is_symlink())
                self.assertEqual((personal / 'unique.txt').read_text(), 'retain unique bytes')
                self.assertTrue(Path(specification['destination']).joinpath('unique.txt').is_file())
        finally:
            # Detach only the two known fixture mountpoints. Never force or recursively
            # delete a tree containing a still-mounted filesystem after cleanup failure.
            safe = True
            if os.path.ismount(manager.root):
                safe = subprocess.run(['hdiutil', 'detach', str(manager.root)], capture_output=True).returncode == 0
            if mounted and safe:
                safe = subprocess.run(['hdiutil', 'detach', str(mount)], capture_output=True).returncode == 0
            if safe:
                import shutil
                shutil.rmtree(root)
            else:
                raise RuntimeError('Fixture detach failed; retained for inspection: ' + str(root))
