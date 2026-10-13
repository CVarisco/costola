from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from core.engine_api import dispatch, APIError
from core.app_manager import AppManager


class EngineAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        (self.home / '.npm').mkdir()
        (self.home / '.npm/file').write_text('data')

    def request(self, command, arguments=None, **extra):
        return {'request_id': 'request-1', 'command': command, 'arguments': arguments or {}, **extra}

    def test_preview_without_image_has_no_filesystem_effects(self):
        before = sorted(str(path.relative_to(self.home)) for path in self.home.rglob('*'))
        result = dispatch(self.request('preview', {'ids': ['npm']}), home=self.home)
        self.assertEqual(result['logical_bytes'], 4)
        self.assertFalse(result['ready'])
        self.assertEqual(result['revision'], 0)
        self.assertEqual(sorted(str(path.relative_to(self.home)) for path in self.home.rglob('*')), before)

    def test_stale_revision_cannot_authorize_another_selection(self):
        dispatch(self.request('select', {'ids': ['npm'], 'revision': 0}, operation_id='select-1'), home=self.home)
        with self.assertRaises(APIError):
            dispatch(self.request('select', {'ids': [], 'revision': 0}, operation_id='select-2'), home=self.home)
        self.assertEqual(dispatch(self.request('status'), home=self.home)['selected'], ['npm'])

    def test_completed_operation_id_returns_same_result_without_second_mutation(self):
        request = self.request('select', {'ids': ['npm'], 'revision': 0}, operation_id='select-1')
        first = dispatch(request, home=self.home)
        second = dispatch(request, home=self.home)
        self.assertEqual(first, second)
        self.assertEqual(dispatch(self.request('status'), home=self.home)['revision'], first['revision'])

    def test_operation_id_cannot_be_reused_for_other_arguments(self):
        dispatch(self.request('select', {'ids': ['npm'], 'revision': 0}, operation_id='same'), home=self.home)
        with self.assertRaises(APIError):
            dispatch(self.request('select', {'ids': [], 'revision': 0}, operation_id='same'), home=self.home)

    def test_unknown_command_does_not_create_state(self):
        with self.assertRaises(APIError):
            dispatch(self.request('arbitrary-shell'), home=self.home)
        self.assertFalse((self.home / 'Library').exists())

    def test_status_matches_shared_swift_protocol_fixture(self):
        fixtures = Path(__file__).parent / 'fixtures/protocol'
        request = json.loads((fixtures / 'requests.json').read_text())[0]
        expected = json.loads((fixtures / 'events.json').read_text())[-1]['data']
        actual = dispatch(request, home=self.home)
        self.assertGreater(actual.pop('internal_free_bytes'), 0)
        expected.pop('internal_free_bytes')
        self.assertEqual(actual, expected)

    def test_confirmed_batch_selects_and_migrates_under_one_request(self):
        def attach_fixture(manager, create=False):
            manager.root.mkdir(parents=True, exist_ok=True)
        request = self.request('migrate', {'ids': ['npm'], 'revision': 0}, operation_id='move-1')
        with patch.object(AppManager, 'attach', attach_fixture), \
                patch.object(AppManager, 'online', return_value=True), \
                patch.object(AppManager, 'check_writers'), patch.object(AppManager, 'check_space'), \
                patch.object(AppManager, 'processes', return_value=[]):
            result = dispatch(request, home=self.home)
            self.assertTrue(result['all_succeeded'])
            self.assertTrue((self.home / '.npm').is_symlink())
            self.assertEqual((self.home / '.npm/file').read_text(), 'data')
            self.assertEqual(dispatch(request, home=self.home), result)
