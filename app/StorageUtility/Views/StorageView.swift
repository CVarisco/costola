import SwiftUI

struct CostolaRootView: View {
    @EnvironmentObject private var model: StorageModel

    var body: some View {
        NavigationSplitView {
            VStack(alignment: .leading, spacing: 22) {
                Label("Costola", systemImage: "externaldrive.fill").font(.title2.bold()).padding(.horizontal, 12)
                List(AppSection.allCases, selection: $model.section) { section in
                    Label(section.rawValue, systemImage: section.icon).tag(section)
                }
                Text("Your files. A little more room.").font(.caption).foregroundStyle(.secondary).padding(12)
            }.padding(.top, 24).navigationSplitViewColumnWidth(min: 190, ideal: 210, max: 260)
        } detail: {
            VStack(spacing: 0) {
                if let notice = model.notice {
                    Label(notice, systemImage: "info.circle").padding().frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.teal.opacity(0.08)).textSelection(.enabled)
                }
                if let error = model.error {
                    HStack(alignment: .top) {
                        Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                        Text(error).textSelection(.enabled)
                        Spacer()
                        Button { model.error = nil } label: { Image(systemName: "xmark") }
                            .buttonStyle(.plain).accessibilityLabel("Dismiss message")
                    }.padding().background(Color.orange.opacity(0.09))
                }
                switch model.section ?? .storage {
                case .storage: StorageView()
                case .operations: OperationsView()
                case .settings: SettingsView()
                }
                if model.isBusy {
                    HStack { ProgressView().controlSize(.small); Text(model.phase); Spacer() }
                        .font(.callout).padding().background(.bar)
                }
            }
            .toolbar {
                Button { Task { await model.refresh() } } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                    .disabled(model.isBusy || model.isLoading)
            }
        }
        .sheet(isPresented: Binding(get: { model.preview != nil }, set: { if !$0 { model.preview = nil } })) {
            if let preview = model.preview { MigrationPreviewView(preview: preview).environmentObject(model) }
        }
        .task {
            await model.refresh()
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds: 5_000_000_000) } catch { break }
                if !model.isBusy { await model.refresh(includeCatalog: false) }
            }
        }
    }
}

struct StorageView: View {
    @EnvironmentObject private var model: StorageModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Make room for what’s next.").font(.largeTitle.weight(.semibold))
                    Text("Move selected developer folders to an external SSD.").foregroundStyle(.secondary)
                }
                if let snapshot = model.snapshot {
                    if snapshot.legacyConflict {
                        Label("An existing storage-script installation was detected. Restore its managed links and disable its agent before setting up Costola.", systemImage: "info.circle")
                            .padding().background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                    }
                    if let device = snapshot.device {
                        HStack(spacing: 16) {
                            Image(systemName: "externaldrive.fill").font(.system(size: 34)).foregroundStyle(.teal)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(device.name).font(.headline)
                                Text(snapshot.online ? "Storage available" : "Storage not mounted").foregroundStyle(.secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 4) {
                                Text(formatBytes(snapshot.internalFreeBytes)).font(.title2.monospacedDigit())
                                Text("free on this Mac").font(.caption).foregroundStyle(.secondary)
                            }
                        }.padding(20).background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                    } else { SetupView() }
                } else if model.isLoading {
                    ProgressView("Loading storage…").padding(.vertical, 30)
                }
                HStack {
                    Text("Folders").font(.title2.weight(.semibold))
                    Spacer()
                    Button { chooseFolder() } label: { Label("Add folder…", systemImage: "plus") }
                        .disabled(model.isBusy || model.snapshot?.legacyConflict == true)
                }
                if model.visibleEntries.isEmpty {
                    VStack(spacing: 10) {
                        Image(systemName: "folder").font(.largeTitle).foregroundStyle(.secondary)
                        Text(model.isLoading ? "Looking for supported folders…" : "No supported folders found")
                        Text("You can add a personal folder. It will require the SSD after moving.")
                            .font(.callout).foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity).padding(32)
                } else {
                    VStack(spacing: 0) {
                        ForEach(model.visibleEntries) { entry in
                            FolderRow(entry: entry)
                            if entry.id != model.visibleEntries.last?.id { Divider().padding(.leading, 48) }
                        }
                    }.background(.background, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary))
                }
                HStack {
                    Text("\(model.newSelectionCount) new folders selected").foregroundStyle(.secondary)
                    Spacer()
                    Button("Review migration") { Task { await model.showPreview() } }
                        .buttonStyle(.borderedProminent)
                        .disabled(model.isBusy || model.newSelectionCount == 0 || model.snapshot?.device == nil || model.snapshot?.legacyConflict == true)
                }
            }.padding(28)
        }
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = false
        panel.prompt = "Add folder"
        panel.message = "Personal folders are kept on the SSD and require it to be connected."
        panel.begin { response in
            if response == .OK, let url = panel.url { Task { await model.addFolder(url) } }
        }
    }
}

private struct FolderRow: View {
    let entry: CatalogEntry
    @EnvironmentObject private var model: StorageModel
    private var managed: Bool { model.snapshot?.paths.contains(where: { $0.id == entry.id }) == true }

    var body: some View {
        HStack(spacing: 14) {
            Toggle(isOn: Binding(get: { model.selection.contains(entry.id) }, set: {
                if $0 { model.selection.insert(entry.id) } else { model.selection.remove(entry.id) }
            })) { Text(entry.name) }.labelsHidden()
                .toggleStyle(.checkbox).accessibilityLabel("Select \(entry.name)")
                .disabled(model.isBusy || managed || entry.status != "available")
            VStack(alignment: .leading, spacing: 4) {
                Text(entry.name).font(.headline)
                Text(entry.source).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                if let reason = entry.reason { Text(reason).font(.caption).foregroundStyle(.orange) }
                else if entry.status == "access-denied" { Text("Access denied — allow folder access in System Settings.").font(.caption).foregroundStyle(.orange) }
                else if entry.status == "linked" && !managed { Text("Already linked — review the existing storage configuration.").font(.caption).foregroundStyle(.orange) }
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 4) {
                Text(managed ? "Managed" : entry.allocatedBytes.map(formatBytes) ?? "—").monospacedDigit()
                Text(entry.kind == "cache" ? "Local cache when offline" : "Requires SSD").font(.caption).foregroundStyle(.secondary)
            }
        }.padding(16)
    }
}
