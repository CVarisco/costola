from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shutil

from core.app_manager import AppManager
from core.preflight import inspect_tree, PreflightError, validate_custom
from core.storage_manager import StorageError


class PreflightTests(unittest.TestCase):
    def test_relative_link_outside_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            source.mkdir()
            (source / 'link').symlink_to('../outside')
            with self.assertRaises(PreflightError):
                inspect_tree(source)

    def test_cloud_folder_is_rejected_without_creating_state(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            folder = home / 'Library/CloudStorage/provider/folder'
            folder.mkdir(parents=True)
            with self.assertRaises(PreflightError):
                validate_custom(home, folder, [])
            self.assertFalse((home / 'Library/Application Support/Costola').exists())

    def test_restore_space_check_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            source = home / 'source'
            source.mkdir()
            (source / 'file').write_text('keep')
            manager = AppManager(home)
            with patch('core.app_manager.shutil.disk_usage', return_value=shutil._ntuple_diskusage(1024, 1024, 0)):
                with self.assertRaises(StorageError):
                    manager.check_space([source], restore=True)
            self.assertEqual((source / 'file').read_text(), 'keep')
