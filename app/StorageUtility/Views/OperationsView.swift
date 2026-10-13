import SwiftUI

struct OperationsView: View {
    @EnvironmentObject private var model: StorageModel
    @State private var showingRestore = false
    @State private var showingDisconnect = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Operations").font(.largeTitle.weight(.semibold))
                Text("Check outcomes and recover interrupted transfers.").foregroundStyle(.secondary)
                ForEach(model.results, id: \.id) { result in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(result.id).font(.headline)
                        Text(result.error ?? result.state).foregroundStyle(result.error == nil ? Color.secondary : .orange)
                    }
                }
                if let snapshot = model.snapshot {
                    if !snapshot.pending.isEmpty {
                        Text("\(snapshot.pending.count) folders are waiting to migrate.")
                        Button("Cancel queued migrations") { Task { await model.cancelPendingMigrations() } }
                            .disabled(model.isBusy)
                    }
                    if snapshot.device != nil {
                        HStack {
                            Button("Connect storage") { Task { await model.connect() } }
                                .disabled(model.isBusy || snapshot.online)
                            Button("Prepare to disconnect…") { showingDisconnect = true }
                                .disabled(model.isBusy || !snapshot.online)
                        }
                        Text("After Costola detaches its storage, eject the physical SSD in Finder before unplugging it.").font(.callout).foregroundStyle(.secondary)
                    }
                    if snapshot.operations.isEmpty { Text("No storage operations yet.").foregroundStyle(.secondary).padding(.vertical) }
                    ForEach(snapshot.operations.reversed()) { operation in
                        HStack(alignment: .top) {
                            Image(systemName: operation.phase == "completed" ? "checkmark.circle" : "arrow.left.arrow.right.circle")
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(operation.entryId) · \(operation.kind)").font(.headline)
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
                    Text("Return to this Mac").font(.title2.weight(.semibold))
                    Text("Copy managed folders back to internal storage. External copies are retained for recovery.").foregroundStyle(.secondary)
                    Button("Restore managed folders…") { showingRestore = true }.disabled(model.isBusy || (snapshot.paths.isEmpty && snapshot.pending.isEmpty))
                }
            }.padding(28)
        }
        .confirmationDialog("Restore managed folders to this Mac?", isPresented: $showingRestore, titleVisibility: .visible) {
            Button("Restore folders") { Task { await model.restore() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Close applications using these folders. Costola checks internal free space, verifies each copy and keeps the external data.")
        }
        .confirmationDialog("Prepare storage for disconnection?", isPresented: $showingDisconnect, titleVisibility: .visible) {
            Button("Prepare to disconnect") { Task { await model.disconnect() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Close tools using managed folders. Caches switch to local storage; personal folders and SDKs require the SSD.")
        }
    }
}
