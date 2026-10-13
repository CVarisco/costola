"""Costola context for the existing storage policies, isolated from legacy state."""
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import uuid

from .catalog import entries as catalog_entries, custom_entry, discover
from .device import disk_info, resolve_volume, validate_volume, DeviceError
from .state import StateStore, StateError, atomic_write
from .storage_manager import Manager


class AppManager(Manager):
    def __init__(self, home=None):
        self.home = Path(home or Path.home()).resolve()
        self.store = StateStore(self.home)
        self.state = self.store.root
        self._has_lock = False
        self._load()

    def _load(self):
        self.document = self.store.read()
        self.entries = list(self.document['entries'].values())
        settings = self.document['settings']
        capacity = shutil.disk_usage(self.home).total
        device = self.document['device'] or {}
        mount = device.get('mount', '')
        self.config = {
            'data_root': str(self.store.mount),
            'physical_mount': mount, 'physical_uuid': device.get('uuid'),
            'image': str(Path(mount) / device.get('image_name', 'unconfigured.sparsebundle')),
            # hdiutil's 'b' suffix means 512-byte sectors, not bytes.
            'image_size': str(device.get('image_size_bytes', 0) // (1024**2)) + 'm',
            'volume_name': 'Costola',
            'cache_budget_bytes': settings['cache_budget_bytes'],
            'warning_free_bytes': capacity * settings['warning_free_percent'] // 100,
            'emergency_free_bytes': capacity * settings['urgent_free_percent'] // 100,
            'log_max_bytes': 5 * 1024**2,
            **self.document.get('runtime', {}),
        }

    @contextlib.contextmanager
    def locked(self):
        with self.store.locked():
            self._load()
            self._has_lock = True
            try:
                yield
            finally:
                self._has_lock = False

    def save(self):
        if not self._has_lock:
            raise StateError('A mutation requires the Costola lock.')
        self.document['entries'] = {entry['id']: entry for entry in self.entries}
        self.document['runtime'] = {
            key: self.config[key] for key in ('data_uuid', 'manual_detached', 'saw_disconnect')
            if key in self.config
        }
        self.document['revision'] += 1
        atomic_write(self.store.path, self.document)

    def fallback(self, source):
        return self.store.fallback / Path(source).absolute().relative_to(self.home)

    def specs(self):
        result = catalog_entries(self.home) + self.document['custom']
        return [{**entry, 'destination': str(self.root / entry['relative_destination'])} for entry in result]

    def discovery(self):
        rows = discover(self.home, self.document['custom'])
        for row in rows:
            row['selected'] = row['id'] in self.document['selected']
            row['managed'] = row['id'] in self.document['entries']
        return rows

    def legacy_conflicts(self):
        registry = self.home / '.ssd-migration/registry.json'
        if registry.exists():
            try:
                value = json.loads(registry.read_text())
                if any(Path(entry['source']).is_symlink() for entry in value.get('entries', [])):
                    return True
            except (OSError, ValueError, KeyError, TypeError):
                return True
        agent = self.home / 'Library/LaunchAgents/com.ssd-migration.switch-links.plist'
        return agent.exists()

    def choose_device(self, path, revision):
        if self.legacy_conflicts():
            raise StateError('Restore legacy links and remove the old agent before setup.')
        device = validate_volume(disk_info(path))

        def update(document):
            old = document['device']
            if old and old['uuid'] == device['uuid']:
                document['device'].update(device)
                return
            if document['entries'] or document['operations']:
                raise StateError('Restore managed folders before changing the disk.')
            device['image_name'] = 'Costola-' + uuid.uuid4().hex + '.sparsebundle'
            document['device'] = device
        self.store.change(revision, update)
        self._load()

    def add_custom(self, source, revision):
        existing = [entry for entry in self.specs() if entry['id'] in self.document['selected']]
        entry = custom_entry(self.home, source, existing + self.document['custom'])
        self.store.change(revision, lambda document: document['custom'].append(entry))
        self._load()
        return entry

    def select(self, ids, revision):
        rows = {entry['id']: entry for entry in self.discovery()}
        known = {key for key, entry in rows.items()
                 if entry['status'] == 'available' or entry['managed']}
        selected_paths = []
        for key in ids:
            if key in rows:
                path = Path(rows[key]['source']).absolute()
                if any(path.is_relative_to(other) or other.is_relative_to(path) for other in selected_paths):
                    raise StateError('Selected folders overlap.')
                selected_paths.append(path)
        self.store.select(ids, known_ids=known, revision=revision)
        self._load()

    def physical_online(self):
        identity = self.config.get('physical_uuid')
        if not identity:
            return False
        try:
            device = resolve_volume(identity)
            self.config['physical_mount'] = device['mount']
            self.config['image'] = str(Path(device['mount']) / self.document['device']['image_name'])
            return True
        except (DeviceError, OSError):
            return False

    def attach(self, create=False):
        if self.legacy_conflicts():
            raise StateError('Legacy storage management is still active.')
        if not self.physical_online():
            raise DeviceError('The selected external disk is unavailable.')
        if Path(self.config['image']).exists() and not self.config.get('data_uuid'):
            raise DeviceError('An unregistered image already exists; preserve it for recovery.')
        super().attach(create=create)

    def configure(self):
        if not self._has_lock:
            raise StateError('Configuration changes require the Costola lock.')
        selected = set(self.document['selected']) & {entry['id'] for entry in self.entries}
        changes = []
        if 'npm' in selected:
            changes.append(('npm', '.npmrc', r'^\s*cache\s*=', 'cache=' + str(self.home / '.npm')))
        if 'pnpm' in selected:
            changes.append(('pnpm', '.npmrc', r'^\s*store-dir\s*=', 'store-dir=' + str(self.home / 'Library/pnpm/store')))
        if 'yarn' in selected:
            changes.append(('yarn', '.yarnrc', r'^\s*cache-folder\s+', 'cache-folder ' + json.dumps(str(self.home / 'Library/Caches/yarn'))))
        for identity, variable, relative in [
            ('homebrew', 'HOMEBREW_CACHE', 'Library/Caches/Homebrew'),
            ('uv', 'UV_CACHE_DIR', '.cache/uv'),
            ('playwright', 'PLAYWRIGHT_BROWSERS_PATH', 'Library/Caches/ms-playwright'),
            ('pip', 'PIP_CACHE_DIR', 'Library/Caches/pip'),
        ]:
            if identity in selected:
                marker = ' # Costola:' + identity
                changes.append((identity, '.zshrc', re.escape(marker) + '$',
                                'export ' + variable + '=' + shlex.quote(str(self.home / relative)) + marker))
        for identity, relative, pattern, replacement in changes:
            if identity in self.document['configuration_changes']:
                continue
            path = self.home / relative
            if path.is_symlink():
                raise StateError('A tool configuration is a symlink; review it before changing paths.')
            before = path.read_text() if path.exists() else ''
            lines = before.splitlines()
            originals = [line for line in lines if re.search(pattern, line)]
            after = '\n'.join([line for line in lines if not re.search(pattern, line)] + [replacement]) + '\n'
            receipt = {'file': relative, 'original_lines': originals, 'introduced_line': replacement,
                       'existed': path.exists(), 'phase': 'prepared'}
            self.document['configuration_changes'][identity] = receipt
            self.save()  # Preserve the inverse before modifying the user's configuration.
            backup = self.state / 'backups/configuration'
            backup.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.exists():
                shutil.copy2(path, backup / (identity + '.original'))
            temporary = path.with_name('.' + path.name + '.costola-' + uuid.uuid4().hex)
            try:
                temporary.write_text(after)
                temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
            receipt['phase'] = 'installed'
            self.save()
