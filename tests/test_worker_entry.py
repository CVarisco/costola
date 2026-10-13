import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


WORKER = Path(__file__).resolve().parents[1] / 'core' / 'worker_entry.py'


class WorkerEntryTests(unittest.TestCase):
    def invoke(self, request):
        with tempfile.TemporaryDirectory(prefix='Costola fixture ') as directory:
            home = Path(directory) / 'home'
            home.mkdir()
            result = subprocess.run(
                [sys.executable, '-B', str(WORKER)],
                input=request,
                capture_output=True,
                text=True,
                cwd=directory,
                env={**os.environ, 'HOME': str(home), 'PATH': ''},
                timeout=10,
            )
            self.assertEqual(list(home.iterdir()), [])
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['home'])
            return result

    def test_info_works_without_checkout_cwd_or_path_and_creates_no_state(self):
        result = self.invoke(json.dumps({
            'protocol_version': 1, 'request_id': 'smoke-1', 'command': 'info',
        }))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])
        self.assertEqual(event['protocol_version'], 1)
        self.assertEqual(event['request_id'], 'smoke-1')
        self.assertEqual(event['type'], 'result')
        self.assertTrue(event['success'])
        self.assertEqual(event['data']['product'], 'Costola')
        self.assertIn('info', event['data']['capabilities'])
        self.assertIn('preview', event['data']['capabilities'])
        self.assertFalse(event['data']['frozen'])

    def test_incompatible_protocol_is_a_failed_result(self):
        result = self.invoke(json.dumps({
            'protocol_version': 99, 'request_id': 'old-client', 'command': 'info',
        }))
        self.assertNotEqual(result.returncode, 0)
        event = json.loads(result.stdout)
        self.assertFalse(event['success'])
        self.assertEqual(event['error']['code'], 'unsupported_protocol')

    def test_unknown_command_is_rejected(self):
        result = self.invoke(json.dumps({
            'protocol_version': 1, 'request_id': 'write-1', 'command': 'unknown-command',
        }))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['error']['code'], 'unsupported_command')

    def test_malformed_input_has_no_traceback_or_success(self):
        result = self.invoke('{')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout)['error']['code'], 'invalid_request')


if __name__ == '__main__':
    unittest.main()
