# Release Costola through GitHub

The public artifact is a Developer ID signed, notarized DMG for each architecture.
No App Store submission is used. A successful source build alone does not qualify
a release. The current development artifacts are ad-hoc signed and are not public
release packages.

## Build inputs

Versions are pinned in packaging/release-manifest.json, requirements-build.txt
and build-settings.xcconfig. Update them together, including bundled runtime
notices. Build with Python 3.14.6 of the target architecture and Xcode with the
macOS SDK. The checked-in Xcode project avoids a release-time XcodeGen dependency.
CI uses explicit macos-15 (arm64) and macos-15-intel runners; it does not infer
architecture from a moving macos-latest label.

## Signing setup

Create a protected GitHub environment named `release`, restricted to version tags
and with maintainer approval. Configure these environment secrets:

- DEVELOPER_ID_P12_BASE64 and DEVELOPER_ID_P12_PASSWORD: exported Developer ID
  Application certificate and private key. An Apple Development identity does not
  substitute for Developer ID.
- DEVELOPER_ID_IDENTITY: the exact Developer ID Application identity name.
- APPLE_ID, APPLE_APP_PASSWORD and APPLE_TEAM_ID: notarization credentials.

Never paste these values into issues, logs or source. The workflow imports them
into an ephemeral keychain and deletes the exported certificate and keychain at
completion. Pull-request checks have read-only contents permission, no signing
secrets and no publication permission.

For a local tagged release, install the signing identity in your keychain and
create a notarytool credential profile. Set COSTOLA_SIGN_IDENTITY,
COSTOLA_NOTARY_PROFILE and COSTOLA_PYTHON, then run scripts/release.sh from a clean
checkout at the matching vVERSION tag. It signs nested code from the inside out,
notarizes and staples the app, builds and notarizes the DMG, checks Gatekeeper and
writes a SHA-256 checksum. Signing or notarization failures stop the build.

## Qualification and publication

The tag workflow runs checks, builds both architectures and creates a **draft**
GitHub release only when both package jobs succeed. Checksums accompany the DMGs.
The maintainer publishes it after recording these additional tests:

- Native Apple Silicon and Intel: macOS 13 and the current supported macOS.
  Rosetta is useful additional evidence, not a replacement for native Intel.
- Download the candidate through a browser with quarantine intact. Install from
  the DMG and launch from Finder with normal Gatekeeper checks.
- In a dedicated account, complete setup, migration, offline routing, reconnect,
  safe disconnect, restore and removal with one cache and one personal folder.
- Test both APFS and exFAT backing volumes, disk renaming, wrong-UUID replacement,
  insufficient space, active writers, permission denial and an interrupted copy.
- Approve, revoke and re-enable the background item; verify an actual sweep after
  login and with the window closed. Test notification consent and delivery.
- Have a developer other than the author complete the flow without terminal help.

Record OS/hardware, source tag, artifact checksums, results and remaining limits.
Do not advertise an untested compatibility row. The public release remains blocked
until signing credentials and this matrix are available and verified.
