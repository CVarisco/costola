from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.catalog import discover, custom_entry, CatalogError


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def test_scan_reports_present_without_creating_absent_paths(self):
        (self.home / '.npm').mkdir()
        (self.home / '.npm/file').write_text('data')
        rows = discover(self.home)
        self.assertEqual([row['id'] for row in rows if row['status'] == 'available'], ['npm'])
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ['.npm'])
        self.assertFalse(any(row.get('selected') for row in rows))

    def test_gradle_maven_protected_configuration_remains_explicit(self):
        rows = {row['id']: row for row in discover(self.home)}
        self.assertEqual(rows['gradle']['prune_subdirs'], ['caches', 'wrapper/dists', 'daemon'])
        self.assertEqual(rows['maven']['prune_subdirs'], ['repository'])
        self.assertEqual(rows['android-sdk']['kind'], 'persistent')

    def test_permission_denied_is_not_absent(self):
        original = Path.lstat
        def stat(path, *args, **kwargs):
            if path == self.home / '.npm':
                raise PermissionError('fixture')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', stat):
            rows = {row['id']: row for row in discover(self.home)}
        self.assertEqual(rows['npm']['status'], 'access-denied')

    def test_custom_folders_are_persistent_and_overlap_is_rejected(self):
        folder = self.home / 'Work'
        folder.mkdir()
        entry = custom_entry(self.home, folder, [])
        self.assertEqual(entry['kind'], 'persistent')
        self.assertEqual(entry['offline'], 'requires-disk')
        with self.assertRaises(CatalogError):
            custom_entry(self.home, folder, [entry])
        with self.assertRaises(CatalogError):
            custom_entry(self.home, self.home, [])

    def test_custom_folder_cannot_escape_home_through_parent_link(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.home / 'alias').symlink_to(outside, target_is_directory=True)
            (Path(outside) / 'folder').mkdir()
            with self.assertRaises(CatalogError):
                custom_entry(self.home, self.home / 'alias/folder', [])
