# Transition from the original storage scripts

Costola does not import or rewrite `~/.ssd-migration` automatically. It detects
legacy managed links and the old LaunchAgent and blocks setup while they remain.
Installing or opening Costola does not disable the script.

Complete and verify the Costola build before changing a working installation.
Record the legacy `tools/storage.sh status` output privately and keep its registry,
configuration and the external image. Check available internal space, close
writers, and preview restoration with `tools/revert-symlinks.sh --dry-run`.

Disable the old automation using `tools/auto-switch-launchagent.sh uninstall`, then restore with
`tools/revert-symlinks.sh`. Check each outcome and verify the restored files before
setting up Costola. If restoration is incomplete, retain the old installation and
its copies; do not make Costola adopt the remaining links. The legacy wrapper
names and usage are documented in their source until the public documentation is
finalized.

When no legacy managed links or agent remain, open Costola, choose the SSD and
explicitly select folders. Review the migration preview and verify one cache and
one persistent folder before expanding the selection. Keep the old external image
as a recovery copy until the transition is verified. Costola creates its own image
and never formats the physical disk.
