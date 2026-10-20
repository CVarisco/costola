"""Versioned local API. No shell command execution or caller-controlled home."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from .app_manager import AppManager
from .device import available_volumes, resolve_volume, DeviceError
from .state import StateError, StateBusyError
from .storage_manager import StorageError, GIB
from .macos_copy import CopyError
from .preflight import PreflightError, inspect_tree


READ_COMMANDS = ('status', 'discover', 'volumes', 'preview')
MUTATIONS = ('choose_device', 'add_custom', 'select', 'setup', 'migrate', 'restore', 'recover', 'settings', 'automation', 'disconnect', 'attach')
BACKGROUND_COMMANDS = ('monitor',)


class APIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def status(manager):
    online = manager.online()
    paths = []
    for entry in manager.entries:
        source = Path(entry['source'])
        target = os.readlink(source) if source.is_symlink() else None
        if target == entry['destination']:
            state = 'external' if online and source.exists() else 'requires-disk'
        elif target == str(manager.fallback(source)) and source.is_dir():
            state = 'local-cache'
        else:
            state = 'needs-attention'
        paths.append({'id': entry['id'], 'source': entry['source'], 'kind': entry['kind'], 'state': state})
    document = manager.document
    result = {
        'revision': document['revision'], 'device': document['device'],
        'online': online, 'selected': document['selected'], 'pending': document['pending'],
        'paths': paths, 'settings': document['settings'],
        'operations': [{'id': item['id'], 'entry_id': item['entry']['id'], 'kind': item['kind'],
                        'phase': item['phase'], 'error': item.get('error')}
                       for item in document['operations'].values()],
        'internal_free_bytes': shutil.disk_usage(manager.home).free,
        'legacy_conflict': manager.legacy_conflicts(),
    }
    result['automation_enabled'] = document.get('automation_enabled', False)
    monitor_path = manager.state / 'monitor-state.json'
    if monitor_path.exists():
        result['background'] = json.loads(monitor_path.read_text())
    return result


def _ids(arguments):
    ids = arguments.get('ids')
    if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        raise APIError('invalid_arguments', 'Choose a list of distinct folder IDs.')
    return ids


def preview(manager, arguments):
    ids = _ids(arguments)
    rows = {entry['id']: entry for entry in manager.discovery()}
    if not set(ids) <= set(rows):
        raise APIError('unknown_folder', 'A selected folder is no longer in the catalog.')
    selected = [rows[key] for key in ids]
    new = [entry for entry in selected if not entry['managed']]
    blockers = [entry['source'] + ': ' + entry['status'] for entry in new if entry['status'] != 'available']
    if not new:
        blockers.append('Select at least one new folder to migrate.')
    for index, entry in enumerate(selected):
        path = Path(entry['source'])
        if any(path.is_relative_to(Path(other['source'])) or Path(other['source']).is_relative_to(path)
               for other in selected[:index]):
            blockers.append('Selected folders overlap.')
    if manager.legacy_conflicts():
        blockers.append('Complete the legacy storage transition before setup.')
    if any(op['phase'] not in ('completed', 'failed') for op in manager.document['operations'].values()):
        blockers.append('Recover the interrupted operation before migrating.')
    logical = sum(entry.get('logical_bytes', 0) for entry in new)
    allocated = sum(entry.get('allocated_bytes', 0) for entry in new)
    required = sum(max(entry.get('logical_bytes', 0), entry.get('allocated_bytes', 0)) for entry in new) + GIB
    free = None
    preliminary = not manager.online()
    if not preliminary:
        specifications = {entry['id']: entry for entry in manager.specs()}
        for entry in new:
            target = Path(specifications[entry['id']]['destination'])
            try:
                if target.is_symlink():
                    blockers.append('An external destination is an unexpected link.')
                elif target.exists():
                    size = inspect_tree(target)
                    required += max(size['logical_bytes'], size['allocated_bytes'])
            except (PreflightError, OSError) as error:
                blockers.append(str(error))
    device = manager.document['device']
    if not device:
        blockers.append('Choose an external disk.')
    else:
        try:
            volume = resolve_volume(device['uuid'])
            free = shutil.disk_usage(volume['mount']).free
            if not preliminary:
                free = min(free, shutil.disk_usage(manager.root).free)
            if free < required:
                blockers.append('The external disk has insufficient free space.')
        except (DeviceError, OSError):
            blockers.append('Connect the selected external disk.')
    return {'revision': manager.document['revision'], 'entries': selected, 'logical_bytes': logical,
            'estimated_reclaimable_bytes': allocated, 'required_bytes': required, 'external_free_bytes': free,
            'preliminary': preliminary, 'ready': not blockers, 'blockers': blockers,
            'note': 'The space you free is an estimate. macOS snapshots and files sharing the same disk data can delay when it appears as free.'}


def _perform(manager, command, arguments):
    revision = manager.document['revision']
    if command == 'disconnect':
        return manager.disconnect()
    if command == 'attach':
        manager.attach()
        return {'online': manager.online()}
    if command == 'automation':
        enabled = arguments.get('enabled')
        if type(enabled) is not bool:
            raise APIError('invalid_arguments', 'Choose whether automation is enabled.')
        if enabled and (not manager.entries or manager.legacy_conflicts()):
            raise StateError('Migrate a folder before enabling automation, and finish any legacy transition.')
        manager.document['automation_enabled'] = enabled
        manager.save()
        return {'enabled': enabled}
    if command == 'choose_device':
        path = arguments.get('path')
        if not isinstance(path, str):
            raise APIError('invalid_arguments', 'Choose an external volume.')
        manager.choose_device(path, revision)
        return {'device': manager.document['device']}
    if command == 'add_custom':
        path = arguments.get('path')
        if not isinstance(path, str):
            raise APIError('invalid_arguments', 'Choose a folder.')
        return {'entry': manager.add_custom(path, revision)}
    if command == 'select':
        manager.select(_ids(arguments), revision)
        return {'selected': manager.document['selected']}
    if command == 'setup':
        manager.attach(create=True)
        return {'online': manager.online()}
    if command == 'migrate':
        if 'ids' in arguments:
            manager.select(_ids(arguments), manager.document['revision'])
            manager.attach(create=True)
        if not manager.online():
            raise StorageError('Connect the selected disk and complete setup first.')
        results = []
        specifications = {entry['id']: entry for entry in manager.specs()}
        for identity in list(manager.document['pending']):
            entry = specifications[identity]
            try:
                manager.migrate(entry, manager.processes())
                results.append({'id': identity, 'state': 'external'})
            except (StorageError, StateError, CopyError, PreflightError, OSError) as error:
                results.append({'id': identity, 'state': 'blocked', 'error': str(error)})
        return {'results': results, 'all_succeeded': all(item['state'] == 'external' for item in results)}
    if command == 'restore':
        results = manager.restore()
        return {'results': results, 'all_succeeded': all(item['state'] == 'restored-external-copy-retained' for item in results)}
    if command == 'recover':
        identity = arguments.get('operation_id')
        if not isinstance(identity, str) or identity not in manager.document['operations']:
            raise APIError('invalid_arguments', 'Choose an interrupted operation.')
        manager.recover(identity)
        return {'operation_id': identity, 'phase': manager.document['operations'][identity]['phase']}
    if command == 'settings':
        settings = arguments.get('settings')
        keys = {'cache_budget_bytes', 'warning_free_percent', 'urgent_free_percent'}
        if not isinstance(settings, dict) or set(settings) != keys or any(type(value) is not int for value in settings.values()):
            raise APIError('invalid_arguments', 'Provide integer cache and free-space settings.')
        if settings['cache_budget_bytes'] < 0 or not 0 <= settings['urgent_free_percent'] < settings['warning_free_percent'] <= 100:
            raise APIError('invalid_arguments', 'The urgent threshold must be lower than the warning threshold.')
        manager.document['settings'] = settings
        manager.save()
        return {'settings': settings}
    raise APIError('unsupported_command', 'Unknown command.')


def dispatch(request, *, home=None, emit=None):
    command = request.get('command')
    arguments = request.get('arguments', {})
    if not isinstance(command, str) or command not in READ_COMMANDS + MUTATIONS + BACKGROUND_COMMANDS:
        raise APIError('unsupported_command', 'Unknown command.')
    if not isinstance(arguments, dict):
        raise APIError('invalid_arguments', 'Arguments must be an object.')
    manager = AppManager(home)
    manager.on_progress = emit
    if command == 'monitor':
        if not manager.document.get('automation_enabled'):
            return {'state': 'disabled'}
        try:
            with manager.locked():
                return manager.monitor()
        except StateBusyError:
            return {'state': 'busy'}
    if command == 'status':
        return status(manager)
    if command == 'discover':
        return {'revision': manager.document['revision'], 'entries': manager.discovery()}
    if command == 'volumes':
        return {'volumes': available_volumes()}
    if command == 'preview':
        return preview(manager, arguments)
    operation_id = request.get('operation_id')
    if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', operation_id):
        raise APIError('invalid_arguments', 'A mutation requires an operation_id.')
    fingerprint = hashlib.sha256(json.dumps([command, arguments], sort_keys=True).encode()).hexdigest()
    with manager.locked():
        receipts = manager.document.setdefault('requests', {})
        previous = receipts.get(operation_id)
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise APIError('operation_conflict', 'This operation_id was used for another request.')
            if previous['phase'] == 'completed':
                return previous['result']
            raise APIError('recovery_required', 'The previous request was interrupted or failed; inspect its outcome first.')
        revision = arguments.get('revision')
        if type(revision) is not int or revision != manager.document['revision']:
            raise APIError('stale_revision', 'State changed; refresh the preview before continuing.')
        receipts[operation_id] = {'fingerprint': fingerprint, 'phase': 'running'}
        manager.save()
        try:
            result = _perform(manager, command, arguments)
            result['revision'] = manager.document['revision'] + 1
            manager.document['requests'][operation_id].update(phase='completed', result=result)
            manager.save()
            return result
        except Exception:
            manager.document['requests'][operation_id]['phase'] = 'failed'
            manager.save()
            raise
