import SwiftUI

struct OperationsView: View {
    @EnvironmentObject private var model: StorageModel
    @State private var showingRestore = false
    @State private var showingDisconnect = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Transfers & recovery").font(.largeTitle.weight(.semibold))
                Text("See which folders moved, resolve problems and recover interrupted transfers.").foregroundStyle(.secondary)
                if !model.results.isEmpty {
                    Text("Latest results").font(.title2.weight(.semibold))
                }
                ForEach(model.results, id: \.id) { result in
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: result.error == nil ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundStyle(result.error == nil ? Color.teal : .orange)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(folderName(result.id)).font(.headline)
                            Text(result.error ?? outcome(result.state)).foregroundStyle(result.error == nil ? Color.secondary : .orange)
                                .textSelection(.enabled)
                        }
                        Spacer()
                        if result.error != nil {
                            Button("Review folders") { model.section = .storage }
                        }
                    }
                    .padding(16).background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
                }
                if let snapshot = model.snapshot {
                    if !snapshot.pending.isEmpty {
                        Text("\(snapshot.pending.count) folders are waiting to move.")
                        Button("Cancel queued moves") { Task { await model.cancelPendingMigrations() } }
                            .disabled(model.isBusy)
                    }
                    if snapshot.device != nil {
                        HStack {
                            Button("Reconnect") { Task { await model.connect() } }
                                .disabled(model.isBusy || snapshot.online)
                            Button("Prepare to disconnect…") { showingDisconnect = true }
                                .disabled(model.isBusy || !snapshot.online)
                        }
                        Text("First prepare the storage here. Then eject the SSD in Finder before unplugging it.").font(.callout).foregroundStyle(.secondary)
                    }
                    Text("Transfer history").font(.title2.weight(.semibold))
                    if snapshot.operations.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("No transfers recorded", systemImage: "arrow.left.arrow.right.circle").font(.headline)
                            Text("After moving folders, you can check their outcomes and recover interrupted transfers here.")
                                .font(.callout).foregroundStyle(.secondary)
                            Button("Choose folders") { model.section = .storage }
                        }.padding(.vertical, 12)
                    }
                    ForEach(snapshot.operations.reversed()) { operation in
                        HStack(alignment: .top) {
                            Image(systemName: operation.phase == "completed" ? "checkmark.circle" : "arrow.left.arrow.right.circle")
                            VStack(alignment: .leading, spacing: 4) {
                                Text(folderName(operation.entryId)).font(.headline)
                                Text(operation.kind.replacingOccurrences(of: "-", with: " ").capitalized).font(.caption).foregroundStyle(.secondary)
                                Text(operation.phase.replacingOccurrences(of: "-", with: " ").capitalized).foregroundStyle(.secondary)
                                if let error = operation.error { Text(error).font(.callout).foregroundStyle(.orange).textSelection(.enabled) }
                            }
                            Spacer()
                            if operation.phase != "completed" && operation.phase != "failed" {
                                Button("Recover") { Task { await model.recover(operation) } }.disabled(model.isBusy)
                            }
                        }.padding().background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
                    }
                    Divider()
                    Text("Move folders back to this Mac").font(.title2.weight(.semibold))
                    Text("Copy the folders you moved back to this Mac. Costola keeps the SSD copies so you can recover them if needed.").foregroundStyle(.secondary)
                    Button("Move folders back…") { showingRestore = true }.disabled(model.isBusy || (snapshot.paths.isEmpty && snapshot.pending.isEmpty))
                }
            }.padding(28)
        }
        .confirmationDialog("Move your folders back to this Mac?", isPresented: $showingRestore, titleVisibility: .visible) {
            Button("Move folders back") { Task { await model.restore() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Close apps using these folders and connect the SSD. Costola checks the space on your Mac, verifies the copies and keeps the SSD copies.")
        }
        .confirmationDialog("Prepare to unplug your SSD?", isPresented: $showingDisconnect, titleVisibility: .visible) {
            Button("Prepare to disconnect") { Task { await model.disconnect() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Close apps using the moved folders. Caches switch to this Mac. Moved SDKs and personal folders will be unavailable until you reconnect the SSD. Then eject the SSD in Finder.")
        }
    }

    private func folderName(_ id: String) -> String {
        if let entry = model.entries.first(where: { $0.id == id }) { return entry.name }
        if let path = model.snapshot?.paths.first(where: { $0.id == id }) {
            return URL(fileURLWithPath: path.source).lastPathComponent
        }
        return id
    }

    private func outcome(_ state: String) -> String {
        switch state {
        case "external": return "Moved to SSD"
        case "restored-external-copy-retained": return "Restored to this Mac · external copy kept"
        default: return state.replacingOccurrences(of: "-", with: " ").capitalized
        }
    }
}
