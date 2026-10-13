"""Verify the actual release DMG, mounted read-only at a private test path."""
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest


class ReleasePackageTests(unittest.TestCase):
    def test_dmg_contains_verified_app_and_installation_shortcut(self):
        dmg = os.environ.get('COSTOLA_RELEASE_DMG')
        if not dmg:
            self.skipTest('Requires a signed and notarized release DMG.')
        root = Path(__file__).resolve().parents[2]
        directory = Path(tempfile.mkdtemp(prefix='costola-release-'))
        mount = directory / 'mount'
        try:
            mount.mkdir()
            subprocess.run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse',
                            '-mountpoint', str(mount), dmg], check=True, capture_output=True)
            try:
                self.assertEqual(os.readlink(mount / 'Applications'), '/Applications')
                self.assertEqual((mount / 'LICENSE.txt').read_bytes(), (root / 'LICENSE').read_bytes())
                subprocess.run([str(root / 'scripts/verify-package.sh'), str(mount / 'Costola.app'),
                                os.environ['COSTOLA_ARCH'], '--release'], check=True)
            finally:
                # Never force-detach or clean up a still-mounted image.
                result = subprocess.run(['/usr/bin/hdiutil', 'detach', str(mount)], capture_output=True)
                if result.returncode:
                    raise RuntimeError('Release test image is still mounted at ' + str(mount))
        finally:
            if not os.path.ismount(mount):
                shutil.rmtree(directory)
