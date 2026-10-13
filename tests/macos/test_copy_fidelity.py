import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from core.macos_copy import copy_tree, verify_tree, CopyError


class CopyFidelityTests(unittest.TestCase):
    def test_copy_preserves_metadata_links_and_existing_directory_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / 'source', root / 'target'
            source.mkdir(mode=0o750)
            target.mkdir(mode=0o700)
            (source / 'first').mkdir()
            (source / 'second').mkdir()
            executable = source / 'first/tool'
            executable.write_text('#!/bin/sh\necho hello\n')
            executable.chmod(0o750)
            subprocess.run(['xattr', '-w', 'user.costola-test', 'metadata', str(executable)], check=True)
            subprocess.run(['xattr', '-w', 'com.apple.ResourceFork', 'resource-fork', str(executable)], check=True)
            subprocess.run(['xattr', '-w', 'user.costola-root', 'root-metadata', str(source)], check=True)
            os.link(executable, source / 'second/hardlink')
            (source / 'relative-link').symlink_to('first/tool')
            subprocess.run(['chmod', '+a', 'everyone deny delete', str(source)], check=True)
            try:
                copy_tree(source, target)
                verify_tree(source, target)
                self.assertEqual((target / 'first/tool').stat().st_ino, (target / 'second/hardlink').stat().st_ino)
                self.assertEqual(subprocess.check_output(['xattr', '-p', 'user.costola-root', str(target)]).strip(), b'root-metadata')
                self.assertEqual(subprocess.check_output(['xattr', '-p', 'com.apple.ResourceFork', str(target / 'first/tool')]).strip(), b'resource-fork')
                self.assertEqual(os.readlink(target / 'relative-link'), 'first/tool')
                subprocess.run(['xattr', '-d', 'user.costola-test', str(target / 'first/tool')], check=True)
                with self.assertRaises(CopyError):
                    verify_tree(source, target)
            finally:
                subprocess.run(['chmod', '-N', str(source), str(target)], check=True)

    def test_persistent_conflict_preserves_both_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.mkdir(); target.mkdir()
            (source / 'config').write_text('local')
            (target / 'config').write_text('external')
            with self.assertRaises(CopyError):
                copy_tree(source, target)
            self.assertEqual((source / 'config').read_text(), 'local')
            self.assertEqual((target / 'config').read_text(), 'external')
