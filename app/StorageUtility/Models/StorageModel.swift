import AppKit
import SwiftUI

enum AppSection: String, CaseIterable, Identifiable {
    case storage = "Storage", operations = "Operations", settings = "Settings"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .storage: return "externaldrive"
        case .operations: return "arrow.left.arrow.right"
        case .settings: return "slider.horizontal.3"
        }
    }
}

@MainActor
final class StorageModel: ObservableObject {
    @Published var section: AppSection? = .storage
    @Published var snapshot: StorageSnapshot?
    @Published var entries: [CatalogEntry] = []
    @Published var volumes: [Volume] = []
    @Published var selection = Set<String>()
    @Published var preview: MigrationPreview?
    @Published var isBusy = false
    @Published var isMutating = false
    @Published var isLoading = false
    @Published var phase = ""
    @Published var error: String?
    @Published var results: [PathResult] = []
    @Published var serviceStatus = BackgroundService.description
    @Published var notice: String?
    private let client: any EngineServing
    private var refreshGeneration = 0
    private var activeMutation: UUID?

    init(client: any EngineServing = EngineClient()) { self.client = client }
    var visibleEntries: [CatalogEntry] { entries.filter { $0.status != "absent" || $0.managed } }
    var newSelectionCount: Int { selection.subtracting(Set(snapshot?.paths.map(\.id) ?? [])).count }

    func refresh(includeCatalog: Bool = true) async {
        serviceStatus = BackgroundService.description
        refreshGeneration += 1
        let generation = refreshGeneration
        isLoading = true
        do {
            async let state: StorageSnapshot = client.request("status", arguments: [:], onProgress: nil)
            if includeCatalog {
                async let catalog: CatalogResponse = client.request("discover", arguments: [:], onProgress: nil)
                async let available: VolumeResponse = client.request("volumes", arguments: [:], onProgress: nil)
                let (newState, newCatalog, newVolumes) = try await (state, catalog, available)
                guard generation == refreshGeneration else { return }
                let previouslyManaged = Set(snapshot?.paths.map(\.id) ?? [])
                if snapshot == nil { selection = Set(newState.selected) }
                selection.subtract(previouslyManaged.subtracting(newState.paths.map(\.id)))
                selection.formIntersection(newCatalog.entries.map(\.id))
                selection.formUnion(newState.selected)
                snapshot = newState
                entries = newCatalog.entries
                volumes = newVolumes.volumes
            } else {
                let newState = try await state
                guard generation == refreshGeneration else { return }
                snapshot = newState
            }
        } catch {
            if generation == refreshGeneration { self.error = error.localizedDescription }
        }
        if generation == refreshGeneration { isLoading = false }
    }

    func showPreview() async {
        guard !isBusy else { return }
        isBusy = true
        error = nil
        phase = "Checking selected folders…"
        do {
            preview = try await client.request("preview", arguments: ["ids": selection.sorted()], onProgress: nil)
        } catch { self.error = error.localizedDescription }
        isBusy = false
        phase = ""
    }

    func confirmMigration() async {
        guard let preview, preview.ready, !isBusy else { return }
        let arguments: [String: Any] = ["ids": preview.entries.map(\.id), "revision": preview.revision]
        self.preview = nil
        await mutate("migrate", arguments: arguments, description: "Preparing migration…")
    }

    func chooseDisk(_ volume: Volume) async {
        guard let snapshot else { return }
        await mutate("choose_device", arguments: ["path": volume.mount, "revision": snapshot.revision], description: "Checking the disk…")
    }

    func addFolder(_ url: URL) async {
        guard let snapshot else { return }
        await mutate("add_custom", arguments: ["path": url.path, "revision": snapshot.revision], description: "Checking the folder…")
    }

    func restore() async {
        guard let snapshot else { return }
        await mutate("restore", arguments: ["revision": snapshot.revision], description: "Preparing restore…")
        if self.snapshot?.paths.isEmpty == true {
            do { try await BackgroundService.disable() }
            catch { self.error = "Folders restored, but the background service could not be removed: " + error.localizedDescription }
            serviceStatus = BackgroundService.description
        }
    }

    func disconnect() async {
        guard let snapshot else { return }
        await mutate("disconnect", arguments: ["revision": snapshot.revision], description: "Preparing safe disconnection…")
    }

    func connect() async {
        guard let snapshot else { return }
        await mutate("attach", arguments: ["revision": snapshot.revision], description: "Connecting storage…")
    }

    func setAutomation(_ enabled: Bool) async {
        guard let snapshot, !isBusy else { return }
        await mutate("automation", arguments: ["enabled": enabled, "revision": snapshot.revision], description: "Updating automation…")
        guard error == nil else { return }
        do {
            if enabled { try BackgroundService.enable() }
            else { try await BackgroundService.disable() }
        } catch { self.error = "Automation service: " + error.localizedDescription }
        serviceStatus = BackgroundService.description
    }

    func enableNotifications() async {
        do {
            if try await !Notifications.authorize() { error = "Notifications are disabled in System Settings." }
        } catch { self.error = error.localizedDescription }
    }

    func recover(_ operation: StorageOperation) async {
        guard let snapshot else { return }
        await mutate("recover", arguments: ["operation_id": operation.id, "revision": snapshot.revision], description: "Checking recoverable copies…")
    }

    func saveSettings(budgetGiB: Double, warning: Int, urgent: Int) async {
        guard let snapshot else { return }
        let bytes = budgetGiB * 1_073_741_824
        guard bytes.isFinite, bytes >= 0, bytes < Double(Int64.max), urgent < warning else {
            error = "Enter a nonnegative cache budget and an urgent threshold below the warning threshold."
            return
        }
        await mutate("settings", arguments: ["revision": snapshot.revision, "settings": [
            "cache_budget_bytes": Int64(bytes), "warning_free_percent": warning, "urgent_free_percent": urgent,
        ]], description: "Saving settings…")
    }

    private func mutate(_ command: String, arguments: [String: Any], description: String) async {
        guard !isBusy else { return }
        isBusy = true
        isMutating = true
        error = nil
        notice = nil
        results = []
        phase = description
        let mutation = UUID()
        activeMutation = mutation
        do {
            let response: MutationResponse = try await client.request(command, arguments: arguments) { [weak self] progress in
                Task { @MainActor in
                    guard let self, self.activeMutation == mutation else { return }
                    self.phase = "\(progress.entryId) · \(progress.phase.replacingOccurrences(of: "-", with: " "))"
                }
            }
            results = response.results ?? []
            notice = response.message
            if response.allSucceeded == false {
                error = "Some folders could not be processed. Open Operations to review each outcome."
                section = .operations
            }
        } catch { self.error = error.localizedDescription }
        await refresh()
        isBusy = false
        isMutating = false
        activeMutation = nil
        phase = ""
    }
}

func formatBytes(_ bytes: Int64) -> String {
    ByteCountFormatter.string(fromByteCount: bytes, countStyle: .binary)
}
