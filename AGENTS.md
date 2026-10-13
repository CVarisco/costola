# Repository Guidelines

## Project Structure & Module Organization

- `core/storage_manager.py` implements verified migration, device checks, cache routing, cleanup, and recovery.
- `core/00-common.sh` provides shared Bash helpers.
- `tools/` contains CLI wrappers, LaunchAgent management, and restore commands.
- `migrations/` contains numbered entry points such as `01-dev-caches.sh`.
- `tests/test_storage_manager.py` contains automated tests.
- `docs/` holds the storage plan and verification notes; `README.md` documents operation and limitations.

## Build, Test, and Development Commands

There is no build step. Use Python 3 and Bash; live storage operations require macOS.

- `python3 -m unittest discover -s tests -v` runs the test suite.
- `for script in core/*.sh tools/*.sh migrations/*.sh; do bash -n "$script" || break; done` checks each shell script's syntax without execution.
- `./tools/storage.sh status` inspects managed storage.
- `./tools/revert-symlinks.sh --dry-run` previews restoration.

Run commands from the repository root. Migration, setup, cleanup, and agent installation change local state; use them only for intentional operational verification.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions, `PascalCase` classes, and uppercase constants. Follow nearby Bash formatting, quote path expansions, and preserve executable shebangs. Use hyphenated shell filenames and retain numbered migration prefixes. No formatter or linter configuration is provided.

## Testing Guidelines

Tests use standard-library `unittest`, temporary directories, and mocks. Name files `test_*.py` and methods `test_<behavior>`. Add regression coverage for changes to copying, conflict handling, symlinks, device identity, offline routing, and recovery. Assert that failures preserve source data. Keep tests isolated from real home directories and disks. No numeric coverage threshold is configured.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout. Use concise, imperative commit subjects, such as `Preserve source files after failed migration`. PRs should describe behavior changes, affected paths, recovery implications, and validation commands. Link relevant issues and update operational documentation when commands or policies change.

## Storage Safety

Verify device identity before writing. Preserve unique files and recoverable backups; stop on persistent-data conflicts. Never treat SDKs, profiles, VM disks, or project files as disposable caches. Keep private runtime state under `~/.ssd-migration/` out of contributions.
