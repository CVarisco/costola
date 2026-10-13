"""Costola context for the existing storage policies, isolated from legacy state."""
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time
import uuid

from .catalog import entries as catalog_entries, custom_entry, discover
from .device import disk_info, resolve_volume, validate_volume, DeviceError
from .state import StateStore, StateError, atomic_write, apply_selection
from .storage_manager import Manager, StorageError, GIB, lexists, run
from .preflight import inspect_tree
from .macos_copy import copy_tree, verify_manifest, sync_tree, manifest


class AppManager(Manager):
    def __init__(self, home=None):
        self.home = Path(home or Path.home()).resolve()
        self.store = StateStore(self.home)
        self.state = self.store.root
        self._has_lock = False
        self.on_progress = None
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

    @property
    def fallback_root(self):
        return self.store.fallback

    def switch_entries(self, entries, online, busy):
        # An unexpected link must never be silently adopted or overwritten.
        safe, results = [], []
        for entry in entries:
            source = Path(entry['source'])
            if source.is_symlink() and os.readlink(source) not in (entry['destination'], str(self.fallback(source))):
                results.append({'source': str(source), 'state': 'blocked', 'reason': 'Unexpected link; inspect before routing.'})
            else:
                safe.append(entry)
        results.extend(super().switch_entries(safe, online, busy))
        for result in results:
            if result['state'] == 'requires-T9':
                result['state'] = 'requires-disk'
        return results

    def fallback_needs_flush(self, entry):
        identity = self.document.get('fallback_sync', {}).get(entry['id'])
        fallback = self.fallback(entry['source'])
        if identity and fallback.is_dir():
            if not re.fullmatch('[a-f0-9]{32}', identity):
                raise StateError('Invalid fallback receipt; preserve local data for inspection.')
            expected = json.loads((self.state / 'manifests' / (identity + '.json')).read_text())
            if manifest(fallback) == expected:
                return False
        return super().fallback_needs_flush(entry)

    @property
    def has_incomplete_operations(self):
        return any(op['phase'] not in ('completed', 'failed') for op in self.document['operations'].values())

    def monitor(self):
        if not self.document.get('automation_enabled'):
            return {'state': 'disabled'}
        if not self._has_lock:
            raise StateError('Monitoring requires the Costola lock.')
        prior_path = self.state / 'monitor-state.json'
        prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
        now = time.time()
        if self.has_incomplete_operations:
            result = {'state': 'recovery-required', 'message': 'Open Costola to recover an interrupted operation.'}
            atomic_write(prior_path, {'checked_at': now, 'result': result})
            return result
        errors = []
        physical = self.physical_online()
        if self.config.get('manual_detached'):
            if not physical and not self.config.get('saw_disconnect'):
                self.config['saw_disconnect'] = True
                self.save()
            elif physical and self.config.get('saw_disconnect'):
                self.config.pop('manual_detached', None)
                self.config.pop('saw_disconnect', None)
                self.save()
        if physical and not self.online() and not self.config.get('manual_detached'):
            try:
                self.attach()
            except (StorageError, StateError, DeviceError, OSError) as error:
                errors.append(str(error))
        online, busy = self.online(), self.processes()
        retries = prior.get('retries', {})
        if online:
            specs = {entry['id']: entry for entry in self.specs()}
            for identity in self.document['pending']:
                if identity not in self.document['selected'] or retries.get(identity, 0) > now:
                    continue
                entry = specs[identity]
                if self.is_busy(entry, busy):
                    continue
                try:
                    self.migrate(entry, busy)
                    retries.pop(identity, None)
                except Exception as error:
                    errors.append(str(error))
                    retries[identity] = now + 3600
                break
        # A failed transfer can leave recoverable copies. Do not prune or reroute them.
        interrupted = self.has_incomplete_operations
        paths = [] if interrupted else self.switch_entries(self.entries, online, busy)
        errors.extend(result['reason'] for result in paths if result['state'] == 'blocked' and 'reason' in result)
        interrupted = self.has_incomplete_operations
        free = shutil.disk_usage(self.home).free
        cleanup = prior.get('cleanup', {})
        last_sweep = prior.get('last_sweep', 0)
        if not interrupted and (now - last_sweep >= 900 or free < self.config['emergency_free_bytes']):
            budget = 0 if free < self.config['emergency_free_bytes'] else self.config['cache_budget_bytes']
            cleanup = self.prune(self.entries, budget, self.processes())
            last_sweep = now
        result = {'state': 'recovery-required' if interrupted else 'checked', 'online': online,
                  'errors': errors, 'paths': paths, 'low_space': free < self.config['warning_free_bytes'],
                  'over_budget': cleanup.get('over_budget', False)}
        changed = result != prior.get('result')
        atomic_write(prior_path, {'checked_at': now, 'result': result, 'last_sweep': last_sweep,
                                 'cleanup': cleanup, 'retries': retries})
        return {**result, 'notify': changed and (bool(errors) or interrupted or result['low_space'] or result['over_budget'])}

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
            if document['entries'] or any(op['phase'] not in ('completed', 'failed') for op in document['operations'].values()):
                raise StateError('Restore managed folders before changing the disk.')
            device['image_name'] = 'Costola-' + uuid.uuid4().hex + '.sparsebundle'
            document['device'] = device
            document['runtime'] = {}
            for key in ('data_uuid', 'manual_detached', 'saw_disconnect'):
                self.config.pop(key, None)
        self._change(revision, update)

    def _change(self, revision, update):
        if self._has_lock:
            if self.document['revision'] != revision:
                raise StateError('Selection changed; refresh the preview.')
            update(self.document)
            self.save()
        else:
            self.store.change(revision, update)
        self._load()

    def add_custom(self, source, revision):
        existing = [entry for entry in self.specs() if entry['id'] in self.document['selected']]
        entry = custom_entry(self.home, source, existing + self.document['custom'])
        self._change(revision, lambda document: document['custom'].append(entry))
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
        self._change(revision, lambda document: apply_selection(document, ids, known))

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

    def check_writers(self, entry, source):
        if self.is_busy(entry, self.processes()):
            raise StorageError('Close the applications using this folder before continuing.')
        if entry.get('custom') or entry['kind'] == 'persistent':
            result = subprocess.run(['/usr/sbin/lsof', '-F', 'p', '+D', str(source)],
                                    capture_output=True, timeout=30)
            if result.stdout:
                raise StorageError('Files in this folder are open in another process.')
            if result.returncode not in (0, 1) or result.stderr:
                raise StorageError('Open-file checks are incomplete; the original will be preserved.')

    def check_space(self, sources, restore=False):
        required = sum(max((size := inspect_tree(path))['logical_bytes'], size['allocated_bytes'])
                       for path in sources) + GIB
        if restore:
            available = shutil.disk_usage(self.home).free
        else:
            if not self.online():
                raise StorageError('The selected disk is unavailable.')
            available = min(shutil.disk_usage(self.root).free,
                            shutil.disk_usage(self.config['physical_mount']).free)
        if available < required:
            raise StorageError('Insufficient space for verified staging and recovery copies.')

    def _phase(self, operation, phase):
        operation['phase'] = phase
        if phase == 'completed':
            operation.pop('error', None)
            operation.pop('failed_phase', None)
        self.save()
        if self.on_progress:
            self.on_progress({'operation_id': operation['id'], 'entry_id': operation['entry']['id'], 'phase': phase})

    @staticmethod
    def _sync_parent(path):
        descriptor = os.open(Path(path).parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _new_operation(self, entry, kind, source, target):
        if not self._has_lock:
            raise StateError('An operation requires the Costola lock.')
        for operation in self.document['operations'].values():
            if operation['entry']['id'] == entry['id'] and operation['phase'] not in ('completed', 'failed'):
                raise StateError('Recover the interrupted operation before retrying this folder.')
        identity = uuid.uuid4().hex
        operation = {
            'id': identity, 'kind': kind, 'entry': entry, 'source': str(source),
            'target': str(target), 'stage': str(target.with_name('.' + target.name + '.costola-' + identity)),
            'backup': str(Path(entry['source']).with_name(Path(entry['source']).name + '.costola-backup-' + identity)),
            'phase': 'prepared',
        }
        self.document['operations'][identity] = operation
        self.save()
        return operation

    def _record_manifest(self, operation, value):
        directory = self.state / 'manifests'
        directory.mkdir(mode=0o700, exist_ok=True)
        atomic_write(directory / (operation['id'] + '.json'), value)

    def migrate(self, entry, busy, local_override=None):
        self.validate_entry(entry)
        if entry['id'] not in self.document['selected']:
            raise StateError('This folder has not been authorized.')
        source, target = Path(entry['source']), Path(entry['destination'])
        if not self.online():
            raise StorageError('The selected disk is unavailable.')
        if target.is_symlink():
            raise StorageError('The external destination is an unexpected symlink.')
        if source.is_symlink() and os.readlink(source) == str(target) and local_override is None:
            if entry['id'] in self.document['entries']:
                return
            raise StateError('An unregistered link requires inspection, not automatic adoption.')
        local = Path(local_override) if local_override is not None else source
        if local_override is not None and local != self.fallback(source):
            raise StateError('Unexpected fallback source.')
        if local.is_symlink() or not local.is_dir():
            raise StorageError('Migration requires a real, accessible source directory.')
        if self.is_busy(entry, busy):
            raise StorageError('An application is using this folder.')
        self.check_writers(entry, local)
        inspect_tree(local)
        self.check_space([local] + ([target] if target.exists() else []))
        operation = self._new_operation(entry, 'migrate', local, target)
        stage, backup = Path(operation['stage']), Path(operation['backup'])
        operation['original_link'] = os.readlink(source) if source.is_symlink() else None
        try:
            self._phase(operation, 'copying')
            if lexists(stage) or lexists(backup):
                raise StorageError('An operation path already exists; preserve it for recovery.')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                copy_tree(target, stage)
            cache_roots = [local / subdir for subdir in entry.get('prune_subdirs', [])] or [local]
            replace = (lambda path: any(path.is_relative_to(root) for root in cache_roots)) if entry['kind'] == 'cache' else None
            expected = copy_tree(local, stage, may_replace=replace)
            sync_tree(stage)
            self._record_manifest(operation, expected)
            self._phase(operation, 'verified')
            self.check_writers(entry, local)
            verify_manifest(expected, local, exact=True)
            if not self.online():
                raise StorageError('Disk disconnected before publication; source preserved.')
            operation['previous'] = str(target.with_name('.' + target.name + '.previous-' + operation['id']))
            self._phase(operation, 'publishing')
            if target.exists():
                if lexists(operation['previous']):
                    raise StorageError('A previous-copy path already exists.')
                target.rename(operation['previous'])
            stage.rename(target)
            self._sync_parent(target)
            self._phase(operation, 'published')
            if not source.is_symlink():
                source.rename(backup)
            self.atomic_link(source, target)
            self._sync_parent(source)
            self.entries = [item for item in self.entries if item['id'] != entry['id']] + [entry]
            self._phase(operation, 'linked')
            self.configure()
            self.check_writers(entry, target)
            if not self.online():
                raise StorageError('Disk disconnected before cleanup; local backup preserved.')
            verify_manifest(expected, target)
            if backup.exists():
                verify_manifest(expected, backup, exact=True)
                if not self.online():
                    raise StorageError('Disk disconnected; backup retained.')
                shutil.rmtree(backup)
            elif local_override is not None:
                verify_manifest(expected, local, exact=True)
                # Retain the fallback as a recoverable copy until a later verified sweep.
                self.document.setdefault('fallback_sync', {})[entry['id']] = operation['id']
            self.document['pending'] = [item for item in self.document['pending'] if item != entry['id']]
            self._phase(operation, 'completed')
        except Exception as error:
            operation['error'] = str(error)
            operation['failed_phase'] = operation['phase']
            self._phase(operation, 'recovery-required')
            raise

    def restore(self, dry_run=False):
        results = []
        if not dry_run:
            # Returning to local storage revokes queued work before the next agent tick.
            self.document['pending'] = []
            self.document['selected'] = [entry['id'] for entry in self.entries]
            self.save()
        for entry in list(self.entries):
            try:
                results.append(self._restore_entry(entry, dry_run))
            except Exception as error:
                results.append({'id': entry['id'], 'state': 'blocked', 'error': str(error)})
        if not dry_run and not self.entries:
            self.document['automation_enabled'] = False
            self.save()
        return results

    def _restore_entry(self, entry, dry_run=False):
        self.validate_entry(entry)
        source = Path(entry['source'])
        if not source.is_symlink():
            raise StorageError('The managed source is no longer its expected link.')
        target = Path(os.readlink(source))
        if target not in (Path(entry['destination']), self.fallback(source)):
            raise StorageError('Unexpected restore link.')
        if not self.online():
            raise StorageError('Connect the selected disk before restoring all managed data.')
        if target == self.fallback(source):
            if dry_run:
                return {'id': entry['id'], 'state': 'would-reconcile-and-restore'}
            routed = self.switch_entries([entry], True, self.processes())
            if not routed or routed[0]['state'] != 'external':
                raise StorageError('Resolve the local cache conflict or active writer before restoring.')
            target = Path(entry['destination'])
        self.check_writers(entry, target)
        self.check_space([target], restore=True)
        if dry_run:
            return {'id': entry['id'], 'state': 'would-restore'}
        operation = self._new_operation(entry, 'restore', target, source)
        stage, backup = Path(operation['stage']), Path(operation['backup'])
        operation['original_link'] = str(target)
        try:
            self._phase(operation, 'copying')
            if lexists(stage) or lexists(backup):
                raise StorageError('Restore staging already exists.')
            expected = copy_tree(target, stage)
            sync_tree(stage)
            self._record_manifest(operation, expected)
            self._phase(operation, 'verified')
            self.check_writers(entry, target)
            verify_manifest(expected, target, exact=True)
            if target == Path(entry['destination']) and not self.online():
                raise StorageError('Disk disconnected; restore copy retained.')
            self._phase(operation, 'publishing')
            source.rename(backup)
            stage.rename(source)
            self._sync_parent(source)
            self._phase(operation, 'published')
            verify_manifest(expected, source)
            self.check_writers(entry, target)
            verify_manifest(expected, target, exact=True)
            self._finish_restore(entry, backup)
            self._phase(operation, 'completed')
            return {'id': entry['id'], 'state': 'restored-external-copy-retained'}
        except Exception as error:
            operation['error'] = str(error)
            operation['failed_phase'] = operation['phase']
            self._phase(operation, 'recovery-required')
            raise

    def _finish_restore(self, entry, backup):
        self.restore_configuration(entry['id'])
        if backup.is_symlink():
            backup.unlink()
        self.entries = [item for item in self.entries if item['id'] != entry['id']]
        self.document['selected'] = [item for item in self.document['selected'] if item != entry['id']]
        self.document['pending'] = [item for item in self.document['pending'] if item != entry['id']]

    def recover(self, operation_id):
        operation = self.document['operations'].get(operation_id)
        if not operation or operation['phase'] in ('completed', 'failed'):
            return
        entry = operation['entry']
        self.validate_entry(entry)
        source = Path(entry['source'])
        backup = source.with_name(source.name + '.costola-backup-' + operation_id)
        if str(backup) != operation['backup'] or not re.fullmatch('[a-f0-9]{32}', operation_id):
            raise StateError('Invalid recovery paths; preserve the operation for inspection.')
        if not lexists(source) and lexists(backup):
            backup.rename(source)
            self._sync_parent(source)
            if operation['kind'] == 'migrate':
                self.entries = [item for item in self.entries if item['id'] != entry['id']]
            self._phase(operation, 'failed')
            return
        phase = operation.get('failed_phase', operation['phase'])
        if (source.is_symlink() and os.readlink(source) == operation.get('original_link') and not lexists(backup)
                and phase in ('prepared', 'copying', 'verified', 'publishing')):
            # The original link is still in place; staging is retained for inspection.
            self._phase(operation, 'failed')
            return
        expected_path = self.state / 'manifests' / (operation_id + '.json')
        if operation['kind'] == 'restore' and source.is_dir() and not source.is_symlink():
            expected = json.loads(expected_path.read_text())
            if not self.online():
                raise StorageError('Reconnect the selected disk to verify restore recovery.')
            self.check_writers(entry, source)
            self.check_writers(entry, Path(operation['source']))
            verify_manifest(expected, Path(operation['source']), exact=True)
            verify_manifest(expected, source, exact=True)
            self._finish_restore(entry, backup)
            self._phase(operation, 'completed')
            return
        if operation['kind'] == 'migrate' and source.is_symlink() and os.readlink(source) == entry['destination']:
            if not self.online():
                raise StorageError('Reconnect the selected disk to verify recovery.')
            expected = json.loads(expected_path.read_text())
            self.check_writers(entry, Path(entry['destination']))
            verify_manifest(expected, Path(entry['destination']))
            self.entries = [item for item in self.entries if item['id'] != entry['id']] + [entry]
            self.configure()
            if backup.exists():
                verify_manifest(expected, backup, exact=True)
                if not self.online():
                    raise StorageError('Disk disconnected; backup retained.')
                shutil.rmtree(backup)
            self.document['pending'] = [item for item in self.document['pending'] if item != entry['id']]
            if operation['source'] == str(self.fallback(source)):
                self.document.setdefault('fallback_sync', {})[entry['id']] = operation_id
            self._phase(operation, 'completed')
            return
        if operation['kind'] == 'migrate' and source.is_dir() and not source.is_symlink() and not lexists(backup):
            # No source replacement occurred. Preserve all staging/external copies.
            self._phase(operation, 'failed')
            return
        raise StateError('Recovery is ambiguous; all copies have been preserved for inspection.')

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
            previous = self.document['configuration_changes'].get(identity)
            if previous and previous['phase'] == 'installed':
                continue
            path = self.home / relative
            if path.is_symlink():
                raise StateError('A tool configuration is a symlink; review it before changing paths.')
            before = path.read_text() if path.exists() else ''
            if previous and previous['phase'] == 'prepared' and previous['introduced_line'] in before.splitlines():
                previous['phase'] = 'installed'
                self.save()
                continue
            lines = before.splitlines()
            originals = [line for line in lines if re.search(pattern, line)]
            after = '\n'.join([line for line in lines if not re.search(pattern, line)] + [replacement]) + '\n'
            receipt = {'file': relative, 'original_lines': originals, 'introduced_line': replacement,
                       'existed': path.exists(), 'pattern': pattern, 'phase': 'prepared'}
            self.document['configuration_changes'][identity] = receipt
            self.save()  # Preserve the inverse before modifying the user's configuration.
            backup = self.state / 'backups/configuration'
            backup.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.exists():
                shutil.copy2(path, backup / (identity + '.original'))
            temporary = path.with_name('.' + path.name + '.costola-' + uuid.uuid4().hex)
            try:
                with temporary.open('w') as stream:
                    stream.write(after)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
                if path.is_symlink() or (path.read_text() if path.exists() else '') != before:
                    raise StateError('Tool configuration changed during setup; retry after closing its writer.')
                os.replace(temporary, path)
                self._sync_parent(path)
            finally:
                if temporary.exists():
                    temporary.unlink()
            receipt['phase'] = 'installed'
            self.save()

    def restore_configuration(self, identity):
        receipt = self.document['configuration_changes'].get(identity)
        if not receipt or receipt['phase'] in ('restored', 'user-modified'):
            return
        if receipt['file'] not in ('.npmrc', '.yarnrc', '.zshrc'):
            raise StateError('Unexpected configuration receipt; preserve it for inspection.')
        path = self.home / receipt['file']
        if path.is_symlink():
            raise StateError('Tool configuration became a symlink; review it before restoring.')
        before = path.read_text() if path.exists() else ''
        lines = before.splitlines()
        introduced = receipt['introduced_line']
        if introduced not in lines:
            # A prepared write may never have happened, or the user chose another value.
            receipt['phase'] = 'user-modified'
            self.save()
            return
        remaining = [line for line in lines if line != introduced]
        pattern = receipt.get('pattern')
        if not pattern or not any(re.search(pattern, line) for line in remaining):
            remaining += receipt['original_lines']
        after = '\n'.join(remaining) + ('\n' if remaining else '')
        temporary = path.with_name('.' + path.name + '.costola-' + uuid.uuid4().hex)
        try:
            with temporary.open('w') as stream:
                stream.write(after)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
            if path.read_text() != before:
                raise StateError('Tool configuration changed during restore; retry after closing its writer.')
            os.replace(temporary, path)
            self._sync_parent(path)
        finally:
            if temporary.exists():
                temporary.unlink()
        receipt['phase'] = 'restored'
        self.save()

    def disconnect(self):
        if self.has_incomplete_operations:
            raise StateError('Recover interrupted operations before disconnecting.')
        if not self.online():
            raise StorageError('Managed storage is not mounted.')
        for entry in self.entries:
            self.check_writers(entry, Path(entry['source']))
            self.snapshot_configuration(entry)
        results = self.switch_entries(self.entries, False, self.processes())
        if any(result['state'] not in ('local-fallback', 'requires-disk') for result in results):
            raise StorageError('Could not prepare every folder for disconnection. Close active tools and retry.')
        # Persist intent before detach so a crash cannot cause an automatic remount.
        self.config['manual_detached'] = True
        self.config['saw_disconnect'] = False
        self.save()
        if not self.online():
            raise StorageError('Storage changed before detach; inspect the disk in Finder.')
        run(['/usr/bin/hdiutil', 'detach', str(self.root)])
        return {'message': 'Managed storage detached. Eject the physical SSD in Finder before unplugging it.'}
