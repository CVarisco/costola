"""Private Costola state. Reads never create directories or load legacy state."""
import contextlib
import copy
import fcntl
import json
import os
from pathlib import Path
import tempfile


class StateError(Exception):
    pass


def atomic_write(path, value):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class StateStore:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.root = self.home / 'Library/Application Support/Costola'
        self.path = self.root / 'state.json'
        self.mount = self.root / 'mount'
        self.fallback = self.root / 'fallback'

    def read(self):
        if not self.path.exists():
            return {
                'version': 1, 'revision': 0, 'device': None,
                'selected': [], 'pending': [], 'entries': {}, 'custom': [],
                'operations': {}, 'configuration_changes': {},
                'settings': {'cache_budget_bytes': 5 * 1024**3,
                             'warning_free_percent': 10, 'urgent_free_percent': 5},
            }
        try:
            value = json.loads(self.path.read_text())
        except (ValueError, OSError) as error:
            raise StateError('State cannot be read; preserve it for recovery.') from error
        if not isinstance(value, dict) or value.get('version') != 1:
            raise StateError('Unsupported state version; use a compatible Costola version.')
        expected = {'revision': int, 'selected': list, 'pending': list, 'entries': dict,
                    'custom': list, 'operations': dict, 'configuration_changes': dict, 'settings': dict}
        if any(type(value.get(key)) is not kind for key, kind in expected.items()):
            raise StateError('Invalid state; preserve it for recovery.')
        return value

    @contextlib.contextmanager
    def locked(self):
        self.read()  # Reject unsupported state before creating a lock file.
        if self.root.is_symlink() or not self.root.parent.resolve().is_relative_to(self.home):
            raise StateError('State directory must remain inside the home directory.')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        with (self.root / 'lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise StateError('Another Costola operation is active.') from error
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def change(self, revision, update):
        with self.locked():
            value = self.read()
            if revision is not None and value['revision'] != revision:
                raise StateError('Selection changed; refresh the preview.')
            result = copy.deepcopy(value)
            update(result)
            result['revision'] += 1
            # A single atomic document commits registry, selection, queue and
            # operation journals together; readers never combine file revisions.
            atomic_write(self.path, result)
            return result

    def select(self, ids, *, known_ids, revision):
        if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
            raise StateError('Selection must contain catalog IDs.')
        if len(set(ids)) != len(ids) or not set(ids) <= set(known_ids):
            raise StateError('Selection contains unknown or duplicate folders.')

        def update(value):
            if set(value['entries']) - set(ids):
                raise StateError('Restore migrated folders before removing them from Costola.')
            if any(op.get('phase') not in ('completed', 'failed') for op in value['operations'].values()):
                raise StateError('Finish or recover the active operation before changing selection.')
            value['selected'] = list(ids)
            value['pending'] = [item for item in ids if item not in value['entries']]
        return self.change(revision, update)
