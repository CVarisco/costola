"""Read-only path inspection used by discovery and migration previews."""
import os
from pathlib import Path
import stat


class PreflightError(Exception):
    pass


def inspect_tree(path):
    """Count logical/allocated bytes without following links or crossing mounts."""
    path = Path(path)
    base = path.lstat()
    result = {'logical_bytes': 0, 'allocated_bytes': 0, 'files': 0}
    seen = set()

    def visit(item):
        metadata = item.lstat()
        if getattr(metadata, 'st_flags', 0) & 0x40000000:  # SF_DATALESS on macOS
            raise PreflightError('Cloud placeholders must not be migrated.')
        if metadata.st_dev != base.st_dev:
            raise PreflightError('Nested volumes cannot be migrated.')
        if stat.S_ISLNK(metadata.st_mode):
            target = Path(os.readlink(item))
            if not target.is_absolute() and not (item.parent / target).resolve().is_relative_to(path.resolve()):
                raise PreflightError('A relative symlink leaves the selected folder.')
            result['allocated_bytes'] += metadata.st_blocks * 512
            return
        if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            raise PreflightError('Special files cannot be migrated.')
        if stat.S_ISDIR(metadata.st_mode):
            result['allocated_bytes'] += metadata.st_blocks * 512
            for child in item.iterdir():
                visit(child)
        elif (metadata.st_dev, metadata.st_ino) not in seen:
            seen.add((metadata.st_dev, metadata.st_ino))
            result['logical_bytes'] += metadata.st_size
            result['allocated_bytes'] += metadata.st_blocks * 512
            result['files'] += 1
    visit(path)
    return result


def validate_custom(home, source, existing):
    home = Path(home).resolve()
    source = Path(source).absolute()
    resolved = source.resolve()
    if not resolved.is_relative_to(home) or resolved == home or source.is_symlink():
        raise PreflightError('Choose a folder inside your home, without a source symlink.')
    excluded = [home / 'Library', home / 'Library/Application Support/Costola',
                home / '.ssd-migration', home / '.ssd-migration-mount', home / '.ssd-migration-fallback',
                home / 'Library/CloudStorage', home / 'Library/Mobile Documents', home / 'Dropbox']
    excluded.extend(home.glob('OneDrive*'))
    if resolved == home / 'Library' or any(
        resolved.is_relative_to(item) or item.is_relative_to(resolved) for item in excluded[1:]
    ):
        raise PreflightError('System, Costola and cloud-managed folders are not supported.')
    if not resolved.is_dir():
        raise PreflightError('Choose an accessible directory.')
    for entry in existing:
        other = Path(entry['source']).resolve()
        if resolved.is_relative_to(other) or other.is_relative_to(resolved):
            raise PreflightError('The folder overlaps another selected or managed folder.')
    inspect_tree(source)
    return source
