# Contributing to Costola

Open an issue describing the user-visible problem, or submit a focused pull
request. Include the behavior change, affected paths, recovery implications and
checks performed. Never include real storage registries, configuration backups,
credentials, certificates, or private files.

Read AGENTS.md and docs/development.md. Python tests use unittest and temporary
homes; Swift tests use the shared Xcode scheme. Run the relevant suites and shell
syntax checks. Live migration and agent installation are not ordinary unit tests:
use a dedicated macOS account and disposable volumes with known fixture data.

Changes to copying, conflicts, device identity, routing, cleanup or recovery need
regression coverage that proves unique source files survive failures. Preserve
macOS metadata and protected Gradle/Maven configuration. Never classify SDKs,
profiles, VM disks or project files as disposable caches.

Changes to the Xcode target structure should update app/project.yml and regenerate
the checked-in project with XcodeGen 2.46.0. End-user dependencies must remain in
the signed app bundle. Keep release signing material outside the repository.

Contributions are provided under the project's MIT license.
