# Managed T9 Storage

The manager moves development data and selected disposable app caches to an APFS sparsebundle on T9, keeps stable home paths, and limits local offline caches. It does not reformat the external drive.

## Commands

Run these from this directory:

```bash
./tools/storage.sh status
./tools/storage.sh setup
./tools/storage.sh migrate
./tools/storage.sh configure
./tools/auto-switch-launchagent.sh install
./tools/storage.sh cleanup
./tools/storage.sh disconnect
./tools/revert-symlinks.sh --dry-run
```

Use `bash tools/storage.sh ...` if executable permissions are missing.

`setup` creates `Development.sparsebundle` on the verified T9 and mounts it at `~/.ssd-migration-mount`. Its 400 GiB capacity is a virtual maximum; backing files grow with stored data. T9's original exFAT files remain intact. There is no physical APFS partition.

`migrate` copies into staging, checks source contents, publishes a destination and replaces the home path only after verification. Unique local data is never discarded merely because a destination exists. Content conflicts stop the affected migration. Partial staging and backups remain recoverable after errors; inspect them before retrying. Only verified source backups are removed. Existing old T9 copies are retained.

Close applications before migrating their data. Active writers are skipped and queued for retry when they stop. The installed agent retries one pending migration at a time. It cannot prevent a new application from starting during a long transfer, so migrations should be run while affected tools are closed.

## Offline policy

Disposable caches switch to local fallback when external storage is unavailable and their writers are idle. SDKs, runtimes and other persistent data keep external links and require T9; the system never silently substitutes empty SDK directories.

The aggregate local fallback cache budget is **5 GiB**. The agent checks routing every **60 seconds** and performs regular cleanup every **15 minutes**. Below **60 GiB** internal free space it attempts immediate cleanup of idle disposable fallback caches. Below **80 GiB** it reports low space and requests a macOS notification. Cache writers are never interrupted: budgets are monitored limits, not hard filesystem quotas, and temporary excess is reported.

Gradle cleanup covers only `caches`, `wrapper/dists` and `daemon`; Maven cleanup covers only `repository`. User configuration in those directories is preserved. App profiles, sessions, recordings, VM disks, SDKs and project files are not disposable caches.

Reconnect flushes fallback data through verified migration. Current disposable cache files replace older disposable copies; unique files are retained. If persistent files or Gradle/Maven configuration disagree, the fallback remains intact and status reports the conflict. A changed directory's source is never deleted without verifying the published copy.

Gradle reconnect uses a separate policy: when idle and the verified T9 volume is available, it preserves configuration and unrecognized files, switches `~/.gradle` to T9, then clears only local `caches`, `wrapper/dists`, and `daemon` contents. Existing external caches are reused; missing dependencies and distributions are downloaded or rebuilt on demand. Conflicting configuration, symlinks in protected data, an unavailable disk, or an active writer stop this operation without discarding local caches. Gradle's per-project `.gradle` and `build` directories remain inside each project. Interrupted staging from an earlier full migration requires inspection before removal.

## Coverage and limitations

Managed caches include npm, yarn, pnpm (both legacy store versions), Homebrew, CocoaPods, DerivedData, Playwright, pip, uv, Gradle, Maven and user CoreSimulator caches. Selected Teams, Notion, Claude, Chrome, Spotify and Cursor cache directories are also managed when idle.

Persistent data includes Android SDK and AVDs, nvm, Cargo, fnm Node versions and Xcode iOS DeviceSupport. System-owned `/Library/Developer/CoreSimulator` data is left alone. Claude's VM and active Codex packages are not relocated.

Moving pnpm's store to another filesystem causes imports into internal projects to use copies rather than hard links. Local `node_modules`, project builds and unmanaged apps can still fill the internal disk. This system does not promise an always-empty internal disk.

Docker's existing external disk is retained. The periodic cache agent does not modify Docker settings or create a local Docker VM. Select a different Docker disk through Docker Desktop's settings; disks selected in different modes contain separate container data. The Docker compatibility command is read-only.

## Safe disconnect

Close affected developer tools and applications, run `tools/storage.sh disconnect`, then eject T9 in Finder. The manager refuses to detach with known active users, prepares cache fallback and asks macOS to detach the APFS image without force. The agent leaves a manually detached image alone until a physical disconnect/reconnect is observed, or `attach` is requested explicitly. Avoid unplugging T9 while the image is mounted.

## Configuration and recovery

Private state is in `~/.ssd-migration/`: `config.json`, `registry.json`, `pending.json`, bounded state log and configuration backups. Legacy `~/.ssd-migration-links.tsv` is retained as migration input. The device UUID prevents accepting another disk that happens to be named T9.

Configuration updates use stable home paths and keep backups under `~/.ssd-migration/backups`. Restart terminals to load changed exports.

The agent's stdout and stderr logs in `~/Library/Logs` retain at most 5 MiB each at each sweep and are only written when routing or error state changes. `launchctl print gui/$(id -u)/com.ssd-migration.switch-links` reports its actual result.

`revert-symlinks.sh` copies current managed data back to internal storage when there is sufficient free space and no known writer. It preserves the external copy for recovery. Remove the agent before a permanent revert:

```bash
./tools/auto-switch-launchagent.sh uninstall
./tools/revert-symlinks.sh --dry-run
./tools/revert-symlinks.sh
```

Legacy VM entry points use the verified manager. Native database data outside your home is deliberately rejected; migrate it separately with service-specific backup and restore. The bulk runner propagates failures instead of claiming success.

## Verification

```bash
python3 -m unittest discover -s tests -v
```

Tests cover unique files, conflicting destinations, failed transfers/links, offline routing, reconnect, quota safety, preserved Gradle configuration, device identity, serialization, restore and bounded logs.
