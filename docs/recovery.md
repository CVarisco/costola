# Recovering Costola storage

Open **Operations** to inspect individual folder outcomes. Close applications
using the affected folder before retrying. An interrupted transfer keeps its
journal and recoverable copies. Choose **Recover**; Costola verifies those copies
before finishing or restoring the original path. Ambiguous copies remain intact
for inspection. Do not delete a `.costola-backup-*`, `.costola-*` staging directory,
or `.previous-*` directory while resolving a failed operation.

Persistent folders and SDKs require the selected SSD. Costola identifies that
volume by UUID and verifies the backing APFS image, not just the Finder name.
Reconnect the original disk if a different disk happens to have the same name.

For an intentional disconnect, choose **Prepare to disconnect** in Operations.
Close any reported writers and retry. When Costola confirms its image is detached,
**eject the physical disk in Finder** before unplugging. Costola never forces a
detach. Automatic checks do not immediately remount a manually detached image;
use **Connect storage**, or physically disconnect and reconnect the disk.

To return to internal storage, connect the SSD and use **Restore managed folders**.
Costola reconciles offline cache data first, stopping on protected-file conflicts, and checks
space and writers for each folder and verifies its staged copy before replacing
the link. A partial restore keeps the remaining folders managed. External copies
are retained. Tool configuration entries still recognizable as Costola's values
are removed or restored; later user edits are preserved. Automation is disabled
only after all folders are restored. A failure to unregister the macOS service is
reported separately; check Settings and macOS Login Items before removing the app.

Use **Cancel queued migrations** in Operations to revoke transfers that have not
started. Unchecking a folder in a new migration draft does not cancel previously
authorized work. Already migrated folders must be restored to leave Costola.

Keep the app and `~/Library/Application Support/Costola` until every folder is
restored and the background item is removed. That private directory contains the
registry, journals, configuration backups and any offline cache/configuration data.
Inspect retained external and local copies before deleting them manually. Do not
attach private state or configuration backups to public GitHub issues.
