# Costola

A macOS utility that moves selected developer folders to an external SSD and
keeps their usual paths working. Choose the disk, select folders, review the
space estimate, and confirm the migration in a native window. The menu bar keeps
storage status within reach.

**Development status:** the implementation is available for development testing.
Public release qualification is incomplete.
There is no validated public DMG yet. The app targets macOS 13 or later with
separate Apple Silicon and Intel packages; the minimum-version and native Intel
matrix must pass before that compatibility is advertised as tested.

## What it does

- Uses an APFS storage image on an external APFS or exFAT volume, without
  formatting the disk. Volume identity and the backing image are checked.
- Discovers supported developer caches and SDKs without selecting them for you.
  Personal folders can be added explicitly; they always require the SSD offline.
- Copies and verifies data and macOS metadata before replacing a source with a
  link. Interrupted operations keep journals and recoverable copies.
- Routes supported caches to private local storage while the disk is unavailable.
  SDKs, profiles, VM disks and project files are never disposable caches.
- Offers opt-in background checks every minute and cache cleanup every 15 minutes.
  The default local cache budget is 5 GiB. Internal free-space warnings start at
  10%, with urgent cleanup below 5%. Active writers can temporarily exceed limits.
- Provides safe disconnection and a verified return to internal storage. External
  copies remain available after restoration.

Gradle cleanup is limited to `caches`, `wrapper/dists` and `daemon`; Maven cleanup
to `repository`. Their configuration is preserved. Gradle reuses existing external
caches on reconnect. Conflicting configuration stops the affected operation.

The built-in catalog includes npm, pnpm, Yarn, Homebrew, CocoaPods, Xcode
DerivedData, Playwright, pip, uv, Bun, Gradle, Maven, selected app caches, Android
SDK/AVDs, nvm, Cargo, fnm and Xcode DeviceSupport. System-owned data and Docker
configuration are outside automatic management. Cross-volume pnpm imports may
use copies instead of hard links; projects and unmanaged applications can still
consume internal space.

## Installation and use

Qualified packages will be published on [GitHub Releases](https://github.com/CVarisco/costola/releases),
not the App Store. Choose the package for your Mac, open the DMG, and drag Costola
to Applications. Public packages must be Developer ID signed and notarized.
No Gatekeeper bypass is part of installation.

1. Open Costola and choose a compatible external SSD.
2. Select folders, review the preview and offline behavior, then confirm.
3. Check individual outcomes in Operations. Close reported writers before retrying.
4. Enable automation and notifications in Settings if desired; approve the
   background item in macOS when requested.
5. Use Prepare to disconnect, then eject the physical disk in Finder.

See [recovery and removal](docs/recovery.md) and the
[legacy-script transition](docs/legacy-transition.md). Existing script users must
restore their managed links and remove the old agent before setting up Costola.

## Development

The app bundles its Python engine; end users do not install Python or Homebrew.
Build instructions and checks are in [development.md](docs/development.md).
Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
Release qualification: [release.md](docs/release.md).

Runtime state stays private under `~/Library/Application Support/Costola`.
Do not include it, configuration backups, credentials or private paths in issues.
Legacy CLI documentation is retained in [legacy-cli.md](docs/legacy-cli.md).

## License

[MIT](LICENSE) © 2026 Christian Varisco. Bundled runtime components retain their
[upstream licenses](packaging/licenses/README.md).
