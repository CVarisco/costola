"""Versioned built-in catalog. Discovery does not authorize a migration."""
import hashlib
from pathlib import Path
import stat

if __package__:
    from .preflight import inspect_tree, validate_custom, PreflightError
else:
    from preflight import inspect_tree, validate_custom, PreflightError

CATALOG_VERSION = 1
ROWS = [
    ('npm', '.npm', 'DevCaches/npm-cache', 'cache', ['npm', 'npm-cli.js', 'pnpm', 'pnpm.cjs', 'yarn'], []),
    ('yarn', 'Library/Caches/yarn', 'DevCaches/yarn-cache', 'cache', ['yarn', 'yarn.js'], []),
    ('pnpm', 'Library/pnpm/store', 'DevCaches/pnpm-store', 'cache', ['pnpm', 'pnpm.cjs'], []),
    ('homebrew', 'Library/Caches/Homebrew', 'DevCaches/Homebrew', 'cache', ['brew', 'ruby'], []),
    ('cocoapods', 'Library/Caches/CocoaPods', 'DevCaches/CocoaPods', 'cache', ['pod', 'ruby'], []),
    ('xcode-derived', 'Library/Developer/Xcode/DerivedData', 'DevCaches/DerivedData', 'cache', ['Xcode', 'xcodebuild', 'swift'], []),
    ('playwright', 'Library/Caches/ms-playwright', 'DevCaches/ms-playwright', 'cache', ['chrome', 'chromium', 'firefox', 'webkit'], []),
    ('pip', 'Library/Caches/pip', 'DevCaches/pip-cache', 'cache', ['pip'], []),
    ('uv', '.cache/uv', 'DevCaches/uv-cache', 'cache', ['uv'], []),
    ('codex-runtimes', '.cache/codex-runtimes', 'DevCaches/codex-runtimes', 'cache', ['codex', 'node_repl'], []),
    ('bun', '.bun/install/cache', 'DevCaches/bun-cache', 'cache', ['bun'], []),
    ('gradle', '.gradle', 'DevCaches/.gradle', 'cache', ['java', 'gradle'], ['caches', 'wrapper/dists', 'daemon']),
    ('maven', '.m2', 'DevCaches/.m2', 'cache', ['java', 'mvn'], ['repository']),
    ('android-sdk', 'Library/Android/sdk', 'SDKs/Android/sdk', 'persistent', ['studio', 'adb', 'java'], []),
    ('android-avd', '.android/avd', 'SDKs/Android/avd', 'persistent', ['emulator', 'qemu'], []),
    ('nvm', '.nvm', 'SDKs/.nvm', 'persistent', ['node'], []),
    ('cargo', '.cargo', 'SDKs/.cargo', 'persistent', ['cargo', 'rustc'], []),
    ('fnm', '.local/share/fnm/node-versions', 'SDKs/fnm-node-versions', 'persistent', ['node'], []),
    ('ios-device-support', 'Library/Developer/Xcode/iOS DeviceSupport', 'SDKs/iOS-DeviceSupport', 'persistent', ['Xcode', 'xcodebuild'], []),
    ('simulator-caches', 'Library/Developer/CoreSimulator/Caches', 'DevCaches/CoreSimulator-Caches', 'cache', ['Simulator', 'CoreSimulator'], []),
    ('teams', 'Library/Containers/com.microsoft.teams2/Data/Library/Caches/Microsoft', 'AppCaches/Teams', 'cache', ['MSTeams', 'Teams'], []),
    ('notion-cache', 'Library/Application Support/Notion/Partitions/notion/Cache', 'AppCaches/Notion', 'cache', ['Notion'], []),
    ('notion-worker', 'Library/Application Support/Notion/Partitions/notion/Service Worker/CacheStorage', 'AppCaches/Notion-CacheStorage', 'cache', ['Notion'], []),
    ('claude', 'Library/Application Support/Claude/Cache', 'AppCaches/Claude', 'cache', ['Claude'], []),
    ('chrome', 'Library/Caches/Google/Chrome', 'AppCaches/Chrome', 'cache', ['Google Chrome', 'chrome'], []),
    ('spotify', 'Library/Caches/com.spotify.client', 'AppCaches/Spotify', 'cache', ['Spotify'], []),
    ('cursor', 'Library/Application Support/Cursor/CachedData', 'AppCaches/Cursor-CachedData', 'cache', ['Cursor'], []),
]


class CatalogError(Exception):
    pass


def entries(home):
    result = []
    for identity, relative, destination, kind, processes, subdirs in ROWS:
        entry = {"id": identity, "source": str(Path(home) / relative),
                 "relative_destination": destination, "kind": kind,
                 "processes": processes, "prune_subdirs": subdirs,
                 "offline": "local-cache" if kind == "cache" else "requires-disk"}
        app = {"notion-cache": "Notion", "notion-worker": "Notion",
               "claude": "Claude", "chrome": "Google Chrome"}.get(identity)
        if app:
            entry["app_bundle"] = "/Applications/" + app + ".app"
        result.append(entry)
    return result


def discover(home, custom=()):
    result = []
    for original in entries(home) + list(custom):
        entry = dict(original)
        source = Path(entry["source"])
        try:
            mode = source.lstat().st_mode
            if stat.S_ISLNK(mode):
                entry["status"] = "linked"
            elif not stat.S_ISDIR(mode):
                entry["status"] = "unsupported"
            else:
                entry.update(inspect_tree(source))
                entry["status"] = "available"
        except FileNotFoundError:
            entry["status"] = "absent"
        except PermissionError:
            entry["status"] = "access-denied"
        except (PreflightError, OSError) as error:
            entry["status"] = "unsupported"
            entry["reason"] = str(error)
        result.append(entry)
    return result


def custom_entry(home, source, existing):
    try:
        path = validate_custom(home, source, existing)
    except (PreflightError, OSError) as error:
        raise CatalogError(str(error)) from error
    identity = "custom-" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    return {"id": identity, "source": str(path), "relative_destination": "Personal/" + identity,
            "kind": "persistent", "processes": [], "prune_subdirs": [],
            "offline": "requires-disk", "custom": True}
