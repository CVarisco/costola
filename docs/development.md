# Costola development

Costola is a macOS app distributed through GitHub Releases. The current bundle
is a development build with disk selection, folder discovery, migration previews,
operation history and recovery controls. Automation and release packaging are
still being completed; do not use it to replace an existing storage installation.

## Build locally

Use Xcode with the macOS SDK and Python **3.14.6** matching the target architecture.
The repository contains the Xcode project; XcodeGen **2.46.0** is needed only to
regenerate it after editing `app/project.yml`.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r packaging/requirements-build.txt
COSTOLA_PYTHON="$PWD/.venv/bin/python" scripts/build-app.sh
```

The app is written to `build/arm64/Xcode/Build/Products/Debug/Costola.app` on
Apple Silicon and to the corresponding `build/x86_64` directory on Intel.
`COSTOLA_ARCH` selects the target; the Python interpreter must have that same
architecture. The build fails on a mismatched interpreter. An Intel build run
through Rosetta is useful development evidence, but does not replace testing
on an Intel Mac or on the oldest supported OS before release.

The worker is a nested, self-contained app bundle. Its resources and Python
libraries remain in PyInstaller's signing-compatible layout. It does not use
the end user's Python, Homebrew, PATH or the source checkout.

Builds use an ad-hoc development signature and the temporary
`com.cvarisco.costola.dev` identity. They are **not notarized public release
packages**. Do not disable Gatekeeper or strip quarantine to distribute them.

## Verify

```bash
.venv/bin/python -B -m unittest discover -s tests -v
xcodebuild test -project app/StorageUtility.xcodeproj -scheme StorageUtility \
  -destination 'platform=macOS' -derivedDataPath build/swift-tests
COSTOLA_APP="$PWD/build/arm64/Xcode/Build/Products/Debug/Costola.app" \
  .venv/bin/python -B -m unittest discover -s tests/macos -v
```

The macOS tests require an already built app; missing assets fail the check.
They relocate the app, remove its worker, alter a sealed resource, and exercise
background launch through a uniquely named temporary SMAppService agent.
The service test registers and unregisters only its own test agent. It does not
install Costola's automation or touch the legacy storage agent. If macOS
requires background-item approval, that test reports a failure rather than
claiming automation works.

All storage paths in automated tests are temporary fixtures. Do not use the
personal SSD or a real developer home as integration-test fixtures.

The legacy scripts continue to use `~/.ssd-migration/config.json`. For a fresh
legacy installation, provide `SSD_MIGRATION_VOLUME_UUID`; the source no longer
contains the author's physical UUID. Costola uses its own private state under
`~/Library/Application Support/Costola` and never imports legacy state silently.
