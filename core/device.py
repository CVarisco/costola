"""Resolve an external volume by UUID, never by its display name."""
from pathlib import Path
import plistlib
import subprocess


class DeviceError(Exception):
    pass


def disk_info(reference):
    result = subprocess.run(
        ['/usr/sbin/diskutil', 'info', '-plist', str(reference)],
        capture_output=True, timeout=30,
    )
    if result.returncode:
        raise DeviceError('The selected disk is unavailable.')
    try:
        return plistlib.loads(result.stdout)
    except (ValueError, plistlib.InvalidFileException) as error:
        raise DeviceError('The disk identity could not be read.') from error


def validate_volume(info):
    mount = info.get('MountPoint')
    uuid = info.get('VolumeUUID')
    filesystem = str(info.get('FilesystemType', '')).lower()
    size = info.get('TotalSize', 0)
    if (not isinstance(mount, str) or not Path(mount).is_absolute()
            or not isinstance(uuid, str) or not uuid
            or info.get('Internal') is not False
            or info.get('ReadOnlyVolume') is True
            or info.get('Writable') is not True
            or filesystem not in ('apfs', 'exfat')
            or type(size) is not int or size <= 2 * 1024**3):
        raise DeviceError('Choose a writable external APFS or exFAT volume with a verifiable identity.')
    return {'uuid': uuid, 'mount': mount, 'name': info.get('VolumeName', Path(mount).name),
            'filesystem': filesystem, 'capacity': size,
            'image_size_bytes': size - 1024**3}


def resolve_volume(uuid, inspect=disk_info):
    volume = validate_volume(inspect(uuid))
    if volume['uuid'] != uuid:
        raise DeviceError('The connected disk does not match the selected disk.')
    return volume


def available_volumes():
    volumes = []
    for path in Path('/Volumes').iterdir():
        try:
            volumes.append(validate_volume(disk_info(path)))
        except (DeviceError, OSError, subprocess.TimeoutExpired):
            continue
    return volumes
