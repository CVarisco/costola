"""Explicit macOS integration gate: registers only a uniquely named test agent."""
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
import uuid


class ServiceRegistrationTests(unittest.TestCase):
    def test_temporary_service_launches_bundled_worker_and_unregisters(self):
        source = Path(os.environ['COSTOLA_APP']).resolve()
        with tempfile.TemporaryDirectory(prefix='Costola service ') as directory:
            root = Path(directory)
            app = root / 'CostolaServiceTest.app'
            shutil.copytree(source, app, symlinks=True)
            label = 'com.cvarisco.costola.test.' + uuid.uuid4().hex
            info_path = app / 'Contents/Info.plist'
            info = plistlib.loads(info_path.read_bytes())
            info.update(CFBundleIdentifier=label, CFBundleExecutable='CostolaServiceTest')
            info_path.write_bytes(plistlib.dumps(info))
            executable = app / 'Contents/MacOS/CostolaServiceTest'
            subprocess.run([
                'xcrun', 'swiftc', str(Path(__file__).with_name('ServiceRegistrationProbe.swift')),
                '-o', str(executable),
            ], check=True, capture_output=True)
            agents = app / 'Contents/Library/LaunchAgents'
            for path in agents.iterdir():
                path.unlink()
            output = root / 'output.json'
            (agents / 'costola-test.plist').write_bytes(plistlib.dumps({
                'Label': label + '.agent',
                'BundleProgram': 'Contents/MacOS/CostolaAgent',
                'RunAtLoad': True,
                'StandardOutPath': str(output),
                'StandardErrorPath': str(root / 'error.log'),
            }))
            # The launcher signature seals the enclosing Info.plist. The fixture
            # changes that identity, so re-sign its launcher before the outer app.
            subprocess.run([
                'codesign', '--force', '--sign', '-', str(app / 'Contents/MacOS/CostolaAgent'),
            ], check=True, capture_output=True)
            subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True, capture_output=True)
            service = 'gui/' + str(os.getuid()) + '/' + label + '.agent'
            try:
                result = subprocess.run(
                    [str(executable), str(output)], capture_output=True, text=True, timeout=30,
                )
                errors = root / 'error.log'
                diagnostic = errors.read_text() if errors.exists() else ''
                self.assertEqual(result.returncode, 0, result.stderr + diagnostic)
                self.assertEqual(result.stderr, '')
                self.assertIn('successfully', result.stdout)
                state = subprocess.run(['launchctl', 'print', service], capture_output=True)
                self.assertNotEqual(state.returncode, 0, 'Test service remained registered')
            finally:
                # This label belongs exclusively to the test; never touch Costola or legacy agents.
                subprocess.run(['launchctl', 'bootout', service], capture_output=True)


if __name__ == '__main__':
    unittest.main()
