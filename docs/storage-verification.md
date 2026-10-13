# Costola verification

## Development evidence — 2026-10-13

Checks use temporary homes, controlled data and disposable disk images. The
existing personal storage script and SSD have not been migrated or disabled.

- Python regression suite: **92 tests passed**, including late writes to a backup,
  interrupted configuration, restore reconciliation and crash recovery. Coverage includes selection authorization, UUID checks, copy verification,
  metadata, recovery, cache routing, cleanup, restore and configuration preservation.
- Swift unit/model tests: **14 tests passed**; JSON-lines protocol, worker failures, preview/confirmation
  separation and visible per-folder failure.
- Native window inspected on the development Mac. A separate test-only app target
  **passed its UI flow test** using the real SwiftUI views with a simulated engine;
  it is not packaged.
- Self-contained arm64 and x86_64 bundles built and probed. Intel execution on this
  host uses Rosetta; it does not establish native Intel compatibility.
- Package integration: **9 tests passed per architecture**; the signed-release DMG
  test is explicitly skipped until signing/notarization are available.
  Packaged-worker tests relocate the bundle, remove the worker and modify sealed
  resources. Invalid/missing resources fail rather than reporting success.
- A uniquely named temporary SMAppService agent starts the packaged worker and is
  unregistered after the test. Costola's real automation is not registered.
- A frozen-worker sweep in an isolated home routes and prunes only its fixture
  cache while preserving a personal file outside it.
- Live hdiutil round trips on disposable APFS and exFAT images cover image creation,
  persistent-folder migration, detach, reconnect, restore and retained external data.
  These prove the filesystem/image path, not physical cable removal or power failure.

## Reproduce

Use docs/development.md for toolchain setup. Run all Python tests, the StorageUtility
Swift scheme, and the StorageFlows UI scheme. UI tests require macOS developer
mode and accessibility automation authorization. Never report an infrastructure
failure to start the UI runner as a passing application test.

For the package and disposable image matrix:

```bash
COSTOLA_APP="$PWD/build/arm64/Xcode/Build/Products/Debug/Costola.app" \
COSTOLA_STORAGE_INTEGRATION=1 python3 -B -m unittest discover -s tests/macos -v
scripts/verify-package.sh "$PWD/build/arm64/Xcode/Build/Products/Debug/Costola.app" arm64
```

The storage integration flag authorizes creation and removal of test-owned images
only. Failed detach preserves the fixture for inspection and never forces a detach.

## Qualification still required

Developer ID signing and notarization, download/Gatekeeper installation, native
Intel and minimum macOS 13 tests, permission revocation and notification delivery
in a dedicated account, physical SSD removal/reconnect, and a separate developer's
usability session remain release gates in docs/release.md. Current development
bundles do not satisfy those gates. The original private rollout notes remain
local and are excluded from Git.
