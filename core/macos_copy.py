"""macOS copy transport and independent verification; never removes a source."""
import ctypes
import errno
import functools
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess


class CopyError(Exception):
    pass


@functools.lru_cache(maxsize=1)
def _libc():
    library = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    library.copyfile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_uint32]
    library.copyfile.restype = ctypes.c_int
    library.acl_get_link_np.argtypes = [ctypes.c_char_p, ctypes.c_int]
    library.acl_get_link_np.restype = ctypes.c_void_p
    library.acl_to_text.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ssize_t)]
    library.acl_to_text.restype = ctypes.c_void_p
    library.acl_free.argtypes = [ctypes.c_void_p]
    library.listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    library.listxattr.restype = ctypes.c_ssize_t
    library.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    library.getxattr.restype = ctypes.c_ssize_t
    return library


def _xattrs(path):
    library = _libc()
    encoded = os.fsencode(path)
    size = library.listxattr(encoded, None, 0, 1)
    if size < 0:
        raise CopyError('Cannot enumerate extended attributes: ' + str(path))
    names = ctypes.create_string_buffer(size or 1)
    count = library.listxattr(encoded, names, size, 1)
    if count != size:
        raise CopyError('Extended attributes changed during inspection: ' + str(path))
    result = {}
    for name in names.raw[:size].split(b'\0'):
        if not name:
            continue
        length = library.getxattr(encoded, name, None, 0, 0, 1)
        if length < 0:
            raise CopyError('Cannot read extended attribute: ' + str(path))
        data = ctypes.create_string_buffer(length or 1)
        if library.getxattr(encoded, name, data, length, 0, 1) != length:
            raise CopyError('Extended attribute changed during inspection: ' + str(path))
        result[os.fsdecode(name)] = hashlib.sha256(data.raw[:length]).hexdigest()
    return result


def _acl(path):
    library = _libc()
    acl = library.acl_get_link_np(os.fsencode(path), 0x100)
    if not acl:
        if ctypes.get_errno() == errno.ENOENT:
            # Darwin filesec_get_property also uses ENOENT for an absent ACL.
            # Recheck the file so disappearance cannot masquerade as an empty ACL.
            Path(path).lstat()
            return ''
        raise CopyError('Cannot inspect ACL: ' + str(path))
    text = None
    try:
        length = ctypes.c_ssize_t()
        text = library.acl_to_text(acl, ctypes.byref(length))
        if not text:
            raise CopyError('Cannot decode ACL: ' + str(path))
        return ctypes.string_at(text, length.value).decode()
    finally:
        if text:
            library.acl_free(text)
        library.acl_free(acl)


def _metadata(source, target):
    # COPYFILE_METADATA | COPYFILE_NOFOLLOW_SRC | COPYFILE_NOFOLLOW_DST
    if _libc().copyfile(os.fsencode(source), os.fsencode(target), None, 7 | (1 << 18) | (1 << 19)):
        raise CopyError('Cannot preserve metadata: ' + str(source))


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def manifest(root):
    root = Path(root)
    items, inodes = {}, {}
    root_device = root.lstat().st_dev

    def visit(path):
        info = path.lstat()
        if info.st_dev != root_device:
            raise CopyError('Nested mounts are not supported.')
        relative = str(path.relative_to(root))
        record = {
            'mode': info.st_mode, 'uid': info.st_uid, 'gid': info.st_gid,
            'mtime_ns': info.st_mtime_ns, 'flags': info.st_flags,
            'acl': _acl(path),
            'xattrs': _xattrs(path),
        }
        if stat.S_ISREG(info.st_mode):
            record['hash'] = _hash(path)
            inodes.setdefault((info.st_dev, info.st_ino), []).append(relative)
        elif stat.S_ISLNK(info.st_mode):
            record['link'] = os.readlink(path)
        elif stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            raise CopyError('Special files are not supported: ' + str(path))
        items[relative] = record
    visit(root)
    groups = sorted(sorted(group) for group in inodes.values() if len(group) > 1)
    return {'items': items, 'hardlinks': groups}


def verify_manifest(expected, target, *, exact=False):
    actual = manifest(target)
    if exact and actual != expected:
        raise CopyError('Source changed after verification; preserve all copies.')
    for relative, metadata in expected['items'].items():
        if actual['items'].get(relative) != metadata:
            raise CopyError('Copy verification failed: ' + relative)
    expected_paths = set(expected['items'])
    actual_groups = sorted(sorted(set(group) & expected_paths) for group in actual['hardlinks']
                           if len(set(group) & expected_paths) > 1)
    if actual_groups != expected['hardlinks']:
        raise CopyError('Hard-link relationships were not preserved.')


def verify_tree(source, target):
    verify_manifest(manifest(source), target)


def sync_tree(root):
    """Flush copied data before a local original can be removed."""
    last_file = None
    for directory, _, files in os.walk(root, followlinks=False):
        for filename in files:
            path = Path(directory) / filename
            if path.is_symlink():
                continue
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
            last_file = path
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    if last_file:
        with last_file.open('rb') as stream:
            fcntl.fcntl(stream.fileno(), fcntl.F_FULLFSYNC)


def copy_tree(source, target, may_replace=None):
    """Merge only into operation-owned staging; conflicts keep both originals."""
    source, target = Path(source), Path(target)
    before = manifest(source)
    environment = {key: value for key, value in os.environ.items() if key != 'DITTONORSRC'}

    def ditto(src, dst):
        if src.is_symlink():
            # ditto follows a symlink supplied as its top-level source argument.
            dst.symlink_to(os.readlink(src))
            return
        result = subprocess.run(
            ['/usr/bin/ditto', '--rsrc', '--extattr', '--acl', str(src), str(dst)],
            capture_output=True, env=environment,
        )
        if result.returncode:
            raise CopyError('Copy failed: ' + str(src))

    def merge(src, dst):
        if not os.path.lexists(dst):
            ditto(src, dst)
        elif src.is_dir() and not src.is_symlink() and dst.is_dir() and not dst.is_symlink():
            for child in src.iterdir():
                merge(child, dst / child.name)
        else:
            relative = str(src.relative_to(source))
            actual = manifest(dst)['items']['.']
            if before['items'][relative] != actual:
                if not may_replace or not may_replace(src):
                    raise CopyError('Conflicting persistent content: ' + str(src))
                if dst.is_dir() and not dst.is_symlink():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
                ditto(src, dst)
        _metadata(src, dst)

    merge(source, target)
    # Separate ditto invocations can split groups spanning merged subtrees.
    for group in before['hardlinks']:
        first = target / group[0]
        for relative in group[1:]:
            other = target / relative
            if first.stat().st_ino != other.stat().st_ino:
                other.unlink()
                os.link(first, other)
    # Restore directory metadata after children. ditto does not retain symlink
    # timestamps, so copy those explicitly without following their targets.
    for relative, metadata in sorted(before['items'].items(), key=lambda item: len(Path(item[0]).parts), reverse=True):
        if stat.S_ISDIR(metadata['mode']) or stat.S_ISLNK(metadata['mode']):
            _metadata(source / relative, target / relative)
        if stat.S_ISLNK(metadata['mode']):
            original = (source / relative).lstat()
            os.utime(target / relative, ns=(original.st_atime_ns, original.st_mtime_ns), follow_symlinks=False)
    if manifest(source) != before:
        raise CopyError('Source changed during copy; retain the original.')
    verify_manifest(before, target)
    return before
