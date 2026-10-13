#!/usr/bin/env python3
"""Managed T9 storage. All deletion is limited to verified copies or cache policy."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

GIB = 1024 ** 3
T9_UUID = os.environ.get('SSD_MIGRATION_VOLUME_UUID', '')
COPY_PROGRESS_TIME = 0
GRADLE_DISPOSABLE = ('caches', 'wrapper/dists', 'daemon')


class StorageError(Exception):
    pass


def run(args):
    result = subprocess.run(args, capture_output=True, timeout=120)
    if result.returncode:
        raise StorageError(result.stderr.decode(errors='replace').strip() or 'Command failed: ' + args[0])
    return result.stdout


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def lexists(path):
    return os.path.lexists(str(path))


def inside(path, root):
    try: Path(path).absolute().relative_to(Path(root).absolute()); return True
    except ValueError: return False


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''): digest.update(block)
    return digest.digest()


def fingerprint(path):
    if path.is_symlink(): return 'link:' + os.readlink(path)
    if path.is_file(): return 'file:' + file_hash(path).hex()
    return None


def same_content(a, b):
    if a.is_symlink() or b.is_symlink():
        return a.is_symlink() and b.is_symlink() and os.readlink(a) == os.readlink(b)
    return a.is_file() and b.is_file() and a.stat().st_size == b.stat().st_size and file_hash(a) == file_hash(b)


def remove_entry(path):
    if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
    else: path.unlink()


def copy_merge(source, target, overwrite=None):
    """Copy without following symlinks or silently overwriting conflicts."""
    global COPY_PROGRESS_TIME
    if time.monotonic() - COPY_PROGRESS_TIME > 30:
        print('Copying data: ' + str(source.parent), flush=True)
        COPY_PROGRESS_TIME = time.monotonic()
    if lexists(target) and overwrite and overwrite(source):
        if source.is_symlink() or not source.is_dir():
            if not same_content(source, target): remove_entry(target)
        elif target.is_symlink() or not target.is_dir(): remove_entry(target)
    if source.is_symlink():
        if lexists(target):
            if not same_content(source, target): raise StorageError('Conflicting symlink: ' + str(source))
        else: target.symlink_to(os.readlink(source))
    elif source.is_dir():
        if lexists(target) and (target.is_symlink() or not target.is_dir()):
            raise StorageError('Conflicting directory: ' + str(source))
        target.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir(): copy_merge(child, target / child.name, overwrite)
        shutil.copystat(source, target, follow_symlinks=False)
    elif source.is_file():
        if lexists(target):
            if not same_content(source, target): raise StorageError('Conflicting file: ' + str(source))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)
    else: raise StorageError('Unsupported special file: ' + str(source))


def verify_copy(source, target):
    if source.is_dir() and not source.is_symlink():
        if target.is_symlink() or not target.is_dir(): raise StorageError('Verification failed: ' + str(source))
        for child in source.iterdir(): verify_copy(child, target / child.name)
    elif not lexists(target) or not same_content(source, target):
        raise StorageError('Verification failed: ' + str(source))


def allocated(path):
    if not lexists(path): return 0
    if path.is_symlink(): return path.lstat().st_blocks * 512
    if path.is_dir(): return path.stat().st_blocks * 512 + sum(allocated(c) for c in path.iterdir())
    return path.stat().st_blocks * 512


def clear_contents(path):
    if path.is_symlink(): raise StorageError('Refusing to clear symlink: ' + str(path))
    if not path.is_dir(): return
    for child in path.iterdir():
        remove_entry(child)


class Manager:
    def __init__(self, home=None):
        self.home = Path(home or Path.home()).absolute()
        self.state = self.home / '.ssd-migration'
        self.config_path = self.state / 'config.json'
        self.registry_path = self.state / 'registry.json'
        self.config = {
            'version': 1, 'physical_mount': '/Volumes/T9', 'physical_uuid': T9_UUID,
            'image': '/Volumes/T9/Development.sparsebundle',
            'data_root': str(self.home / '.ssd-migration-mount'), 'image_size': '400g',
            'cache_budget_bytes': 5 * GIB, 'warning_free_bytes': 80 * GIB,
            'emergency_free_bytes': 60 * GIB, 'log_max_bytes': 5 * 1024 * 1024,
        }
        if self.config_path.exists(): self.config.update(json.loads(self.config_path.read_text()))
        self.entries = json.loads(self.registry_path.read_text()).get('entries', []) if self.registry_path.exists() else []

    @property
    def root(self): return Path(self.config['data_root'])

    @contextlib.contextmanager
    def locked(self):
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state.chmod(0o700)
        with (self.state / 'lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def save(self):
        atomic_json(self.config_path, self.config)
        atomic_json(self.registry_path, {'version': 1, 'entries': self.entries})

    @property
    def fallback_root(self): return self.home / '.ssd-migration-fallback'

    def fallback(self, source):
        rel = Path(source).absolute().relative_to(self.home)
        return self.fallback_root / 'Users' / self.home.name / rel

    def validate_entry(self, e):
        src, dst = Path(e['source']), Path(e['destination'])
        if not inside(src, self.home) or src == self.home or not inside(dst, self.root) or dst == self.root:
            raise StorageError('Unsafe registry entry: ' + str(src))
        if '..' in src.parts or '..' in dst.parts or e['kind'] not in ('cache', 'persistent'):
            raise StorageError('Invalid path policy: ' + str(src))
        if not inside(src.parent.resolve(), self.home.resolve()):
            raise StorageError('Source parent escapes home: ' + str(src))
        if not inside(dst.parent.resolve(), self.root.resolve()):
            raise StorageError('Destination parent escapes managed volume: ' + str(dst))

    def disk_info(self, path):
        return plistlib.loads(run(['/usr/sbin/diskutil', 'info', '-plist', str(path)]))

    def physical_online(self):
        try:
            info = self.disk_info(self.config['physical_mount'])
            return info.get('MountPoint') == self.config['physical_mount'] and info.get('VolumeUUID') == self.config['physical_uuid']
        except (StorageError, OSError, ValueError): return False

    def online(self):
        if not self.physical_online(): return False
        try:
            info = self.disk_info(self.root)
            if info.get('MountPoint') != str(self.root) or info.get('FilesystemType') != 'apfs': return False
            if self.config.get('data_uuid') != info.get('VolumeUUID'): return False
            images = plistlib.loads(run(['/usr/bin/hdiutil', 'info', '-plist'])).get('images', [])
            return any(str(Path(i.get('image-path', '')).resolve()) == str(Path(self.config['image']).resolve())
                       and any(x.get('mount-point') == str(self.root) for x in i.get('system-entities', [])) for i in images)
        except (StorageError, OSError, ValueError): return False

    def attach(self, create=False):
        if not self.physical_online(): raise StorageError('Verified T9 is not mounted')
        if self.online():
            self.root.chmod(0o700)
            if self.config.pop('manual_detached', None) is not None: self.save()
            return
        image = Path(self.config['image'])
        if not inside(image, Path(self.config['physical_mount'])): raise StorageError('Image must be on T9')
        if not image.exists():
            if not create: raise StorageError('Managed APFS image does not exist; run setup')
            run(['/usr/bin/hdiutil', 'create', '-size', self.config['image_size'], '-type', 'SPARSEBUNDLE', '-fs', 'APFS', '-volname', self.config.get('volume_name', 'T9-Development'), str(image)])
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.set_aside_stray_mountpoint_data()
        if os.path.ismount(self.root) or any(self.root.iterdir()): raise StorageError('Managed mountpoint is occupied by an unexpected volume or local data')
        run(['/usr/bin/hdiutil', 'attach', '-nobrowse', '-mountpoint', str(self.root), str(image)])
        info = self.disk_info(self.root)
        uuid = info.get('VolumeUUID')
        if info.get('FilesystemType') != 'apfs' or not uuid: raise StorageError('APFS validation failed')
        if self.config.get('data_uuid') and self.config['data_uuid'] != uuid: raise StorageError('Unexpected APFS volume identity')
        self.config['data_uuid'] = uuid
        self.config.pop('manual_detached', None)
        self.config.pop('saw_disconnect', None)
        self.save()
        if not self.online(): raise StorageError('Image backing storage validation failed')
        self.root.chmod(0o700)

    def set_aside_stray_mountpoint_data(self):
        # Tools following a persistent link while the image is detached (e.g. a Gradle daemon)
        # write into the bare mountpoint and would block every later attach. Keep their data, but out of the way.
        if os.path.ismount(self.root) or not any(self.root.iterdir()): return
        backup = self.state / 'backups' / ('mountpoint-' + time.strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(mode=0o700, parents=True)
        for child in list(self.root.iterdir()): shutil.move(str(child), str(backup / child.name))
        print('Moved stray mountpoint data to ' + str(backup), file=sys.stderr, flush=True)

    def processes(self):
        # Keep only executable/script identities, never credentials or raw arguments.
        identities = run(['/bin/ps', '-axo', 'comm=']).decode(errors='replace').splitlines()
        arguments = run(['/bin/ps', '-axo', 'args=']).decode(errors='replace').splitlines()
        for line in arguments:
            try: words = shlex.split(line)
            except ValueError: continue
            for word in words[:4]:
                name = Path(word).name.lower()
                if name in ('npm', 'npm-cli.js', 'pnpm', 'pnpm.cjs', 'yarn', 'yarn.js', 'uv', 'pip', 'pip3', 'pod', 'mvn', 'gradle'):
                    identities.append(name)
        return identities

    def is_busy(self, e, busy):
        if e.get('app_bundle'):
            bundle = Path(e['app_bundle'])
            return any(inside(Path(p.strip()), bundle) or Path(p.strip()).name == bundle.stem
                       or Path(p.strip()).name.startswith(bundle.stem + ' Helper') for p in busy)
        names = [Path(p.strip()).name.lower() for p in busy]
        return any(name == token.lower() or name.startswith(token.lower() + ' ')
                   for token in e.get('processes', []) for name in names)

    def atomic_link(self, source, target):
        source.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink() and os.readlink(source) == str(target): return False
        if lexists(source) and not source.is_symlink(): raise StorageError('Source is not a symlink: ' + str(source))
        tmp = source.with_name('.' + source.name + '.ssd-link-' + str(os.getpid()))
        if lexists(tmp): raise StorageError('Temporary link already exists: ' + str(tmp))
        try:
            tmp.symlink_to(target, target_is_directory=True)
            os.replace(tmp, source)
        finally:
            if lexists(tmp): tmp.unlink()
        return True

    def migrate(self, e, busy, local_override=None):
        self.validate_entry(e)
        src, dst = Path(e['source']), Path(e['destination'])
        if local_override is None and src.is_symlink() and os.readlink(src) == str(dst) and dst.is_dir():
            if e not in self.entries: self.entries.append(e); self.save()
            return
        if self.is_busy(e, busy): raise StorageError('Active writer; migration postponed: ' + e['source'])
        # Never assume a symlink means migration is complete.
        local = Path(local_override) if local_override is not None else Path(os.readlink(src)) if src.is_symlink() else src
        if src.is_symlink() and not local.is_absolute(): local = src.parent / local
        allowed = (self.home, self.root, Path(self.config['physical_mount']))
        if local.exists() and not any(inside(local.resolve(), r.resolve()) for r in allowed):
            raise StorageError('Unexpected source link target: ' + str(local))
        dst.parent.mkdir(parents=True, exist_ok=True)
        stage = dst.parent / ('.' + dst.name + '.staging')
        # An interrupted stage remains a recoverable copy, never a reason to erase source.
        if stage.exists(): raise StorageError('Interrupted staging requires inspection: ' + str(stage))
        source_backup = None
        published_backup = None
        original_link = os.readlink(src) if src.is_symlink() else None
        try:
            stage.mkdir()
            sources = []
            if dst.exists(): sources.append(dst)
            seed = Path(e.get('legacy_destination', '')) if e.get('legacy_destination') else None
            local_populated = local.is_dir() and any(local.iterdir())
            if seed and seed.exists() and seed != dst and seed != local and not local_populated: sources.append(seed)
            if local.exists(): sources.append(local)
            required = sum(allocated(p) for p in sources)
            backing = Path(self.config['physical_mount'])
            available = shutil.disk_usage(dst.parent).free
            if backing.exists(): available = min(available, shutil.disk_usage(backing).free)
            if available < required + 256 * 1024 * 1024:
                raise StorageError('Not enough external free space: ' + str(dst))
            for source in sources:
                overwrite = None
                if source == local and e['kind'] == 'cache':
                    cache_roots = [local / sub for sub in (e.get('prune_subdirs') or ['.'])]
                    overwrite = lambda path: any(inside(path, root) for root in cache_roots)
                copy_merge(source, stage, overwrite)
                verify_copy(source, stage)
            if e.get('processes') or e.get('app_bundle'):
                if self.is_busy(e, self.processes()):
                    raise StorageError('Writer started during transfer; source preserved: ' + e['source'])
            if dst.exists():
                published_backup = dst.with_name('.' + dst.name + '.previous-' + str(int(time.time())))
                if published_backup.exists(): raise StorageError('Previous backup already exists')
                dst.rename(published_backup)
            stage.rename(dst)
            if lexists(src) and not src.is_symlink():
                source_backup = src.with_name(src.name + '.ssd-migration-backup-' + str(int(time.time())))
                if lexists(source_backup): raise StorageError('Source backup already exists')
                src.rename(source_backup)
            self.atomic_link(src, dst)
            if e not in self.entries:
                self.entries = [item for item in self.entries if item['source'] != e['source']] + [e]
            self.save()
            # Only a verified local source copy may be removed. Legacy external copies stay.
            if source_backup:
                verify_copy(source_backup, dst)
                shutil.rmtree(source_backup)
            elif local.exists() and inside(local, self.fallback_root):
                verify_copy(local, dst)
                clear_contents(local)
            if published_backup: shutil.rmtree(published_backup)
        except Exception:
            if source_backup and source_backup.exists():
                if src.is_symlink(): src.unlink()
                if not lexists(src): source_backup.rename(src)
            elif original_link is not None and not src.is_symlink():
                src.symlink_to(original_link)
            # Preserve published/partial external copies for diagnosis; never discard source.
            raise

    def switch_entries(self, entries, online, busy):
        results = []
        for e in entries:
            try:
                self.validate_entry(e)
                src, dst = Path(e['source']), Path(e['destination'])
                if not src.is_symlink():
                    results.append({'source': str(src), 'state': 'needs-migration'}); continue
                if self.is_busy(e, busy):
                    results.append({'source': str(src), 'state': 'active-writer'}); continue
                fallback = self.fallback(src)
                fallback_root = self.fallback_root
                if fallback_root.is_symlink(): raise StorageError('Fallback root must not be a symlink')
                fallback_root.mkdir(mode=0o700, parents=True, exist_ok=True)
                fallback_root.chmod(0o700)
                if fallback.is_symlink() or not inside(fallback.resolve(), fallback_root.resolve()):
                    raise StorageError('Unsafe fallback path: ' + str(fallback))
                if online:
                    if not dst.is_dir():
                        results.append({'source': str(src), 'state': 'external-target-missing'}); continue
                    if e['kind'] == 'cache' and src == self.home / '.gradle' and fallback.is_dir():
                        self.reconnect_gradle(e)
                    elif e['kind'] == 'cache' and self.fallback_needs_flush(e):
                        # Reconnect is a verified migration, retaining conflicts for manual review.
                        self.migrate(e, busy, local_override=fallback)
                    else: self.atomic_link(src, dst)
                    self.snapshot_configuration(e)
                    results.append({'source': str(src), 'state': 'external'})
                elif e['kind'] == 'cache':
                    fallback.mkdir(parents=True, exist_ok=True)
                    self.atomic_link(src, fallback)
                    results.append({'source': str(src), 'state': 'local-fallback'})
                else:
                    # Keep an external link: never substitute an empty SDK or VM.
                    self.atomic_link(src, dst)
                    results.append({'source': str(src), 'state': 'requires-T9'})
            except (StorageError, OSError) as error:
                results.append({'source': e['source'], 'state': 'blocked', 'reason': str(error)})
        return results

    def reconnect_gradle(self, e):
        """Retain configuration and external caches; discard only idle local caches."""
        self.validate_entry(e)
        src, dst = Path(e['source']), Path(e['destination'])
        if src != self.home / '.gradle' or e['kind'] != 'cache':
            raise StorageError('Gradle reconnect requires the registered Gradle cache')
        base = self.fallback(src)
        fallback_root = self.fallback_root
        if fallback_root.is_symlink() or base.is_symlink() or not inside(base.resolve(), fallback_root.resolve()):
            raise StorageError('Unsafe Gradle fallback')
        roots = [base / rel for rel in GRADLE_DISPOSABLE]
        if any(root.is_symlink() or not inside(root.resolve(), base.resolve()) for root in roots):
            raise StorageError('Gradle cache symlink requires inspection')
        if not self.online() or not dst.is_dir():
            raise StorageError('Verified external Gradle storage is unavailable')
        if self.is_busy(e, self.processes()):
            raise StorageError('Active Gradle writer; reconnect postponed')
        stamp_path = self.state / 'configuration-snapshots.json'
        stamps = json.loads(stamp_path.read_text()) if stamp_path.exists() else {}
        preserved = []

        def inspect(source, target):
            if source in roots: return  # Never enumerate, hash or copy disposable cache files.
            if source.is_symlink() or target.is_symlink():
                raise StorageError('Gradle configuration symlink requires inspection: ' + str(source))
            if source.is_dir():
                if lexists(target) and not target.is_dir():
                    raise StorageError('Conflicting Gradle directory: ' + str(source))
                preserved.append((source, target, True))
                for child in source.iterdir(): inspect(child, target / child.name)
            elif source.is_file():
                # An unchanged offline snapshot must not overwrite newer external configuration.
                if target.is_file() and stamps.get(str(source)) == fingerprint(source): return
                if lexists(target) and not same_content(source, target):
                    raise StorageError('Conflicting Gradle file: ' + str(source))
                preserved.append((source, target, False))
            else:
                raise StorageError('Unsupported Gradle file: ' + str(source))

        inspect(base, dst)
        for source, target, directory in preserved:
            if directory: target.mkdir(parents=True, exist_ok=True)
            else:
                copy_merge(source, target)
                verify_copy(source, target)
        self.snapshot_configuration(e)
        if not self.online() or self.is_busy(e, self.processes()):
            raise StorageError('Gradle storage or writer state changed; local cache preserved')
        self.atomic_link(src, dst)
        for root in roots: clear_contents(root)

    def fallback_needs_flush(self, e):
        fallback = self.fallback(e['source'])
        if not fallback.is_dir(): return False
        stamp_path = self.state / 'configuration-snapshots.json'
        stamps = json.loads(stamp_path.read_text()) if stamp_path.exists() else {}
        for directory, dirs, files in os.walk(fallback, followlinks=False):
            for name in dirs:
                if (Path(directory) / name).is_symlink(): return True
            for name in files:
                path = Path(directory) / name
                if str(path) not in stamps or fingerprint(path) != stamps[str(path)]: return True
        return False

    def snapshot_configuration(self, e):
        """Keep known small tool configuration available offline, never prune it."""
        names = {'.gradle': ['gradle.properties', 'init.gradle', 'init.gradle.kts', 'init.d'],
                 '.m2': ['settings.xml', 'settings-security.xml', 'toolchains.xml']}.get(Path(e['source']).name, [])
        if not names: return
        stamp_path = self.state / 'configuration-snapshots.json'
        stamps = json.loads(stamp_path.read_text()) if stamp_path.exists() else {}
        external = Path(e['destination'])
        fallback = self.fallback(e['source'])
        for name in names:
            source = external / name
            if not lexists(source): continue
            leaves = [source]
            if source.is_dir() and not source.is_symlink():
                leaves = [p for p in source.rglob('*') if p.is_file() or p.is_symlink()]
            for leaf in leaves:
                if leaf.is_symlink(): raise StorageError('Configuration symlink needs manual review: ' + str(leaf))
                rel = leaf.relative_to(external)
                target = fallback / rel
                key = str(target)
                current = fingerprint(target)
                incoming = fingerprint(leaf)
                if current is not None and current != incoming and stamps.get(key) != current:
                    raise StorageError('Local configuration changed; compare before overwriting: ' + str(target))
                target.parent.mkdir(parents=True, exist_ok=True)
                if current != incoming: shutil.copy2(leaf, target)
                stamps[key] = incoming
        atomic_json(stamp_path, stamps)

    def prune(self, entries, budget, busy):
        candidates = []
        for e in entries:
            self.validate_entry(e)
            if e['kind'] != 'cache': continue
            base = self.fallback(e['source'])
            if base.is_symlink() or not inside(base.resolve(), (self.fallback_root).resolve()):
                raise StorageError('Fallback directory escapes managed storage: ' + str(base))
            roots = [base / sub for sub in (e.get('prune_subdirs') or ['.'])]
            for root in roots:
                if not inside(root.resolve(), base.resolve()) or root.is_symlink(): continue
                if root.is_dir(): candidates.append((root.stat().st_mtime, root, e, allocated(root)))
        total = sum(item[3] for item in candidates)
        removed = 0
        for _, root, e, size in sorted(candidates, key=lambda x: x[0]):
            if total <= budget: break
            if self.is_busy(e, busy): continue
            clear_contents(root)
            removed += size; total -= size
        return {'remaining_bytes': total, 'removed_bytes': removed, 'budget_bytes': budget, 'over_budget': total > budget}

    def restore(self, dry_run=False):
        busy = self.processes()
        results = []
        for e in list(self.entries):
            self.validate_entry(e)
            src = Path(e['source'])
            if not src.is_symlink():
                results.append({'source': str(src), 'state': 'already-local'}); continue
            target = Path(os.readlink(src))
            if target != Path(e['destination']) and target != self.fallback(src):
                raise StorageError('Unexpected restore link: ' + str(src))
            if not target.is_dir(): raise StorageError('Restore source unavailable: ' + str(target))
            if self.is_busy(e, busy): raise StorageError('Active writer prevents restore: ' + str(src))
            if dry_run:
                results.append({'source': str(src), 'from': str(target), 'state': 'would-restore'}); continue
            if shutil.disk_usage(self.home).free < allocated(target) + GIB:
                raise StorageError('Insufficient internal storage for restore: ' + str(src))
            staging = src.with_name(src.name + '.restore-staging')
            if lexists(staging): raise StorageError('Restore staging already exists: ' + str(staging))
            copy_merge(target, staging); verify_copy(target, staging)
            src.unlink()
            try: staging.rename(src)
            except OSError:
                src.symlink_to(target); raise
            self.entries.remove(e); self.save()
            # Retain external copy for rollback/recovery.
            results.append({'source': str(src), 'state': 'restored-external-copy-retained'})
        return results

    def specs(self):
        if __package__:
            from .catalog import ROWS
        else:
            try:
                from core.catalog import ROWS
            except ModuleNotFoundError as error:
                if error.name != 'core':
                    raise
                from catalog import ROWS
        rows = [row[1:] for row in ROWS]
        entries = []
        legacy_file = self.home / '.ssd-migration-links.tsv'
        legacy = {}
        if legacy_file.exists():
            for line in legacy_file.read_text().splitlines():
                fields = line.split('\t')
                if len(fields) >= 2: legacy[fields[0]] = fields[1]
        for rel, dest, kind, processes, subdirs in rows:
            source = str(self.home / rel)
            entry = {'source': source, 'destination': str(self.root / dest), 'kind': kind, 'processes': processes}
            app_bundles = {
                'Notion': '/Applications/Notion.app',
                'Claude': '/Applications/Claude.app',
                'Chrome': '/Applications/Google Chrome.app',
            }
            app_name = dest.split('/')[-1].removesuffix('-CacheStorage')
            if app_name in app_bundles: entry['app_bundle'] = app_bundles[app_name]
            if subdirs: entry['prune_subdirs'] = subdirs
            old = legacy.get(source, str(Path(self.config['physical_mount']) / 'Volumes' / dest))
            if old and inside(Path(old), Path(self.config['physical_mount']) / 'Volumes'):
                entry['legacy_destination'] = old
            entries.append(entry)
        return entries

    def configure(self):
        # Backups are kept once per run; never print unrelated config values.
        stamp = str(int(time.time()))
        backup = self.state / 'backups' / stamp
        backup.mkdir(parents=True, exist_ok=True)
        npmrc = self.home / '.npmrc'
        text = npmrc.read_text() if npmrc.exists() else ''
        if npmrc.exists(): shutil.copy2(npmrc, backup / 'npmrc')
        lines = [line for line in text.splitlines() if not line.strip().startswith(('cache=', 'cache =', 'store-dir=', 'store-dir ='))]
        lines += ['cache=' + str(self.home / '.npm'), 'store-dir=' + str(self.home / 'Library/pnpm/store')]
        npmrc.write_text('\n'.join(lines) + '\n')
        yarnrc = self.home / '.yarnrc'
        if yarnrc.exists():
            shutil.copy2(yarnrc, backup / 'yarnrc')
            lines = [line for line in yarnrc.read_text().splitlines() if not line.strip().startswith('cache-folder ')]
            lines.append('cache-folder ' + json.dumps(str(self.home / 'Library/Caches/yarn')))
            yarnrc.write_text('\n'.join(lines) + '\n')
        zshrc = self.home / '.zshrc'
        if zshrc.exists():
            shutil.copy2(zshrc, backup / 'zshrc')
            text = zshrc.read_text()
            mapping = {
                '/Volumes/T9/Volumes/SDKs/Android/sdk': str(self.home / 'Library/Android/sdk'),
                '/Volumes/T9/Volumes/SDKs/Android/avd': str(self.home / '.android/avd'),
                '/Volumes/T9/Volumes/SDKs/.nvm': str(self.home / '.nvm'),
                '/Volumes/T9/Volumes/SDKs/.cargo': str(self.home / '.cargo'),
            }
            for old, new in mapping.items():
                source = Path(new)
                if source.is_symlink() and inside(Path(os.readlink(source)), self.root) and source.exists():
                    text = text.replace(old, new)
            begin, end = '# BEGIN T9 MANAGED CACHE PATHS', '# END T9 MANAGED CACHE PATHS'
            if begin in text and end in text:
                left, rest = text.split(begin, 1); _, right = rest.split(end, 1); text = left + right
            text += '\n' + begin + '\n'
            for key, rel in [('HOMEBREW_CACHE', 'Library/Caches/Homebrew'), ('UV_CACHE_DIR', '.cache/uv'), ('PLAYWRIGHT_BROWSERS_PATH', 'Library/Caches/ms-playwright'), ('PIP_CACHE_DIR', 'Library/Caches/pip')]:
                text += 'export ' + key + '=' + json.dumps(str(self.home / rel)) + '\n'
            text += end + '\n'
            zshrc.write_text(text)
        self.save()

    def docker_status(self):
        result = {}
        for filename in ('settings.json', 'settings-store.json'):
            path = self.home / 'Library/Group Containers/group.com.docker' / filename
            try:
                if path.exists():
                    data = json.loads(path.read_text()); result[filename] = {'diskPath': data.get('diskPath'), 'state': 'manual-managed'}
            except (OSError, ValueError): result[filename] = {'state': 'access-denied-or-invalid'}
        return result

    def health(self):
        is_online = self.online()
        paths = []
        for e in self.entries:
            src = Path(e['source'])
            target = os.readlink(src) if src.is_symlink() else None
            paths.append({'source': str(src), 'kind': e['kind'], 'target': target, 'available': src.exists(),
                          'state': 'external' if target == e['destination'] and is_online else 'requires-T9' if target == e['destination'] and e['kind'] == 'persistent' else 'local-fallback' if target == str(self.fallback(src)) else 'needs-attention'})
        pending_path = self.state / 'pending.json'
        pending = json.loads(pending_path.read_text()).get('entries', []) if pending_path.exists() else []
        return {'external_online': is_online, 'T9_present': self.physical_online(), 'pending_migrations': [e['source'] for e in pending],
                'internal_free_GiB': round(shutil.disk_usage(self.home).free / GIB, 1),
                'cache_budget_GiB': self.config['cache_budget_bytes'] / GIB,
                'paths': paths, 'docker': self.docker_status()}

    def rotate_logs(self):
        for suffix in ('.log', '.error.log'):
            path = self.home / ('Library/Logs/com.ssd-migration.switch-links' + suffix)
            if path.exists() and path.stat().st_size > self.config['log_max_bytes']:
                # Truncate in place so launchd's open descriptor does not keep writing an unlinked file.
                with path.open('r+b') as stream:
                    stream.seek(max(0, path.stat().st_size - self.config['log_max_bytes']))
                    tail = stream.read(); stream.seek(0); stream.write(tail); stream.truncate()

    def monitor(self):
        self.rotate_logs()
        prior_path = self.state / 'monitor-state.json'
        prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
        error = None
        physical = self.physical_online()
        if self.config.get('manual_detached') and not physical:
            self.config['saw_disconnect'] = True; self.save()
        if self.config.get('manual_detached') and physical and self.config.get('saw_disconnect'):
            self.config.pop('manual_detached'); self.config.pop('saw_disconnect'); self.save()
        if physical and not self.online() and not self.config.get('manual_detached'):
            try: self.attach()
            except (StorageError, OSError) as exc: error = str(exc)
        online = self.online()
        busy = self.processes()  # Unknown process state must not allow deletion.
        pending_path = self.state / 'pending.json'
        pending = json.loads(pending_path.read_text()).get('entries', []) if pending_path.exists() else []
        # Retry one previously authorized migration when its writers have stopped.
        if online:
            for e in list(pending):
                if self.is_busy(e, busy) or e.get('retry_after', 0) > time.time(): continue
                try:
                    self.migrate(e, busy)
                    self.configure()
                    pending.remove(e)
                    atomic_json(pending_path, {'entries': pending})
                except (StorageError, OSError) as exc:
                    error = str(exc)
                    e['retry_after'] = time.time() + 3600
                    e['last_error'] = error
                    atomic_json(pending_path, {'entries': pending})
                break
        results = self.switch_entries(self.entries, online, busy)
        free = shutil.disk_usage(self.home).free
        cleanup = prior.get('cleanup', {})
        if time.time() - prior.get('last_sweep', 0) >= 900 or free < self.config['emergency_free_bytes']:
            cache_entries = {e['source']: e for e in self.entries + pending}
            cleanup = self.prune(list(cache_entries.values()), 0 if free < self.config['emergency_free_bytes'] else self.config['cache_budget_bytes'], busy)
            last_sweep = time.time()
        else: last_sweep = prior.get('last_sweep', 0)
        state = {'online': online, 'error': error, 'paths': results,
                 'low_space': free < self.config['warning_free_bytes'], 'over_budget': cleanup.get('over_budget', False)}
        if state != prior.get('state'):
            print(json.dumps(state), flush=True)
            if state['low_space'] or state['over_budget']:
                message = 'Spazio interno sotto 80 GiB. Controlla storage.sh status.' if state['low_space'] else 'Cache offline oltre il limite: chiudi gli strumenti attivi per consentire la pulizia.'
                try:
                    subprocess.run(['/usr/bin/osascript', '-e', 'display notification ' + json.dumps(message) + ' with title "Gestione spazio T9"'], capture_output=True, timeout=10)
                except (OSError, subprocess.TimeoutExpired): pass
        atomic_json(prior_path, {'state': state, 'last_sweep': last_sweep, 'cleanup': cleanup})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'attach', 'migrate', 'move', 'restore', 'monitor', 'status', 'switch', 'cleanup', 'disconnect', 'configure'])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--source')
    parser.add_argument('--destination')
    parser.add_argument('--mode', choices=['auto', 'ssd', 'fallback'], default='auto')
    parser.add_argument('--category', choices=['cache', 'persistent', 'all'], default='all')
    args = parser.parse_args(argv)
    manager = Manager()
    if args.command == 'status': print(json.dumps(manager.health(), indent=2)); return 0
    with manager.locked():
        if args.command in ('setup', 'attach'): manager.attach(create=args.command == 'setup')
        elif args.command == 'configure': manager.configure()
        elif args.command == 'restore': print(json.dumps(manager.restore(args.dry_run), indent=2))
        elif args.command == 'move':
            if not args.source or not args.destination: raise StorageError('move requires source and destination')
            if not manager.online(): raise StorageError('Verified APFS storage is unavailable')
            entry = {'source': args.source, 'destination': args.destination, 'kind': 'persistent',
                     'processes': ['qemu', 'prl_vm_app', 'vmware-vmx', 'postgres', 'mysqld', 'mongod', 'redis-server']}
            manager.migrate(entry, manager.processes())
        elif args.command == 'migrate':
            if not manager.online(): raise StorageError('Verified APFS storage must be mounted before migrating')
            busy = manager.processes()
            failures = []
            pending = []
            for e in manager.specs():
                if args.category != 'all' and e['kind'] != args.category: continue
                if e['kind'] == 'persistent' and not lexists(Path(e['source'])) and not Path(e.get('legacy_destination', '/nonexistent')).exists(): continue
                print('Migrating ' + e['source'], flush=True)
                try:
                    manager.migrate(e, manager.processes()); print('OK ' + e['source'], flush=True)
                except (StorageError, OSError) as exc:
                    failures.append({'source': e['source'], 'reason': str(exc)}); print('BLOCKED ' + str(exc), flush=True)
                    pending.append(e)
            atomic_json(manager.state / 'migration-result.json', {'failures': failures, 'date': time.time()})
            pending_path = manager.state / 'pending.json'
            old_pending = json.loads(pending_path.read_text()).get('entries', []) if pending_path.exists() else []
            processed = {e['source'] for e in manager.specs() if args.category == 'all' or e['kind'] == args.category}
            pending = [e for e in old_pending if e['source'] not in processed] + pending
            atomic_json(pending_path, {'entries': pending})
            return 1 if failures else 0
        elif args.command == 'monitor': manager.monitor()
        elif args.command == 'switch':
            online = manager.online() if args.mode == 'auto' else args.mode == 'ssd'
            if online and not manager.online(): raise StorageError('Verified external storage is unavailable')
            print(json.dumps(manager.switch_entries(manager.entries, online, manager.processes()), indent=2))
        elif args.command == 'cleanup': print(json.dumps(manager.prune(manager.entries, manager.config['cache_budget_bytes'], manager.processes())))
        elif args.command == 'disconnect':
            if not manager.online(): raise StorageError('Managed external volume is not mounted')
            busy = manager.processes()
            if any(manager.is_busy(e, busy) for e in manager.entries): raise StorageError('Close tools using managed data before disconnecting')
            results = manager.switch_entries(manager.entries, False, busy)
            if any(r['state'] == 'blocked' for r in results): raise StorageError('Could not prepare all fallback links')
            run(['/usr/bin/hdiutil', 'detach', str(manager.root)])
            manager.config['manual_detached'] = True
            manager.config['saw_disconnect'] = False
            manager.save()
            print('Managed image detached. Eject T9 in Finder before unplugging it.')
    return 0


if __name__ == '__main__':
    try: sys.exit(main())
    except (StorageError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print('Storage error: ' + str(exc), file=sys.stderr)
        sys.exit(1)
