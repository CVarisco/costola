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
                Text("Developer folders on your SSD.").font(.caption).foregroundStyle(.secondary).padding(12)
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
                    .help("Refresh disk status and available folders")
            }
        }
        .tint(.teal)
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
    @State private var choosingDisk = false

    private var selectedEntries: [CatalogEntry] {
        model.visibleEntries.filter { entry in
            model.selection.contains(entry.id) && model.snapshot?.paths.contains(where: { $0.id == entry.id }) != true
        }
    }

    private var selectionHint: String {
        if model.snapshot?.device == nil { return "Choose an external disk before reviewing." }
        let selected = selectedEntries
        if selected.isEmpty { return "Review the space estimate before moving anything." }
        let measuredBytes = selected.reduce(Int64(0)) { $0 + ($1.allocatedBytes ?? 0) }
        return "\(formatBytes(measuredBytes)) measured · final estimate in review"
    }

    var body: some View {
        VStack(spacing: 0) {
            folderContent
            Divider()
            selectionBar
        }
    }

    private var folderContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Free up space on your Mac.").font(.largeTitle.weight(.semibold))
                    Text("Move developer caches, SDKs and personal folders to an external SSD. Your tools keep using the same folder paths.").foregroundStyle(.secondary)
                }
                if let snapshot = model.snapshot {
                    if snapshot.paths.isEmpty {
                        HStack(spacing: 18) {
                            setupStep(1, "Choose a disk", complete: snapshot.device != nil)
                            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                            setupStep(2, "Select folders", complete: model.newSelectionCount > 0)
                            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                            setupStep(3, "Review & move", complete: false)
                        }.padding(.vertical, 4).accessibilityElement(children: .combine)
                    }
                    if snapshot.legacyConflict {
                        Label("An existing storage-script installation was detected. Restore its managed links and disable its agent before setting up Costola.", systemImage: "info.circle")
                            .padding().background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                    }
                    if let device = snapshot.device {
                        HStack(spacing: 16) {
                            Image(systemName: "externaldrive.fill").font(.system(size: 34)).foregroundStyle(.teal)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(device.name).font(.headline)
                                Label(snapshot.online ? "SSD storage ready" : "SSD storage unavailable",
                                      systemImage: snapshot.online ? "checkmark.circle.fill" : "eject.circle")
                                    .font(.callout).foregroundStyle(snapshot.online ? Color.teal : .secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 4) {
                                Text(formatBytes(snapshot.internalFreeBytes)).font(.title2.monospacedDigit())
                                Text("free on this Mac").font(.caption).foregroundStyle(.secondary)
                            }
                        }.padding(20).background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                        if !snapshot.online {
                            HStack(alignment: .top) {
                                Label("Connect your selected SSD, then click Reconnect. Moved SDKs and personal folders need the SSD to work.", systemImage: "info.circle")
                                    .font(.callout).foregroundStyle(.secondary)
                                Spacer()
                                Button("Reconnect") { Task { await model.connect() } }.disabled(model.isBusy)
                            }
                        }
                        if snapshot.paths.isEmpty {
                            Button(choosingDisk ? "Keep current disk" : "Choose another disk…") { choosingDisk.toggle() }
                                .disabled(model.isBusy)
                            if choosingDisk { SetupView() }
                        }
                    } else { SetupView() }
                } else if model.isLoading {
                    ProgressView("Loading storage…").padding(.vertical, 30)
                } else {
                    Label("Storage status is unavailable. Refresh to try again.", systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.secondary)
                }
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("Folders").font(.title2.weight(.semibold))
                        Spacer()
                        Button { chooseFolder() } label: { Label("Add folder…", systemImage: "plus") }
                            .disabled(model.isBusy || model.snapshot == nil || model.snapshot?.legacyConflict == true)
                    }
                    Text("Select only the folders you want to move. Nothing moves until you review and confirm.")
                        .font(.callout).foregroundStyle(.secondary)
                    Text("Without the SSD: supported caches use a local cache. Moved SDKs and personal folders are unavailable.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                if model.visibleEntries.isEmpty {
                    VStack(spacing: 10) {
                        Image(systemName: "folder").font(.largeTitle).foregroundStyle(.secondary)
                        Text(model.isLoading ? "Looking for supported folders…" : "No developer folders found")
                        Text("Add a personal folder to move it to the SSD. You will need the SSD connected to use it.")
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
            }.padding(28)
        }
    }

    private var selectionBar: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text(model.newSelectionCount == 0 ? "No new folders selected" : "\(model.newSelectionCount) \(model.newSelectionCount == 1 ? "folder" : "folders") selected")
                    .font(.headline)
                Text(selectionHint)
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Button("Review selected folders") { Task { await model.showPreview() } }
                .buttonStyle(.borderedProminent).controlSize(.large)
                .disabled(model.isBusy || model.newSelectionCount == 0 || model.snapshot?.device == nil || model.snapshot?.legacyConflict == true)
        }.padding(.horizontal, 28).padding(.vertical, 16).background(.bar)
    }

    private func setupStep(_ number: Int, _ title: String, complete: Bool) -> some View {
        HStack(spacing: 8) {
            ZStack {
                Circle().fill(complete ? Color.teal.opacity(0.14) : Color.secondary.opacity(0.10)).frame(width: 26, height: 26)
                if complete { Image(systemName: "checkmark").foregroundStyle(.teal) }
                else { Text("\(number)").foregroundStyle(.secondary) }
            }
            Text(title).font(.callout.weight(.medium))
        }
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = false
        panel.prompt = "Add folder"
        panel.message = "After moving, this folder will need the SSD connected. Costola keeps its usual path working."
        panel.begin { response in
            if response == .OK, let url = panel.url { Task { await model.addFolder(url) } }
        }
    }
}

private struct FolderRow: View {
    let entry: CatalogEntry
    @EnvironmentObject private var model: StorageModel
    private var managed: Bool { model.snapshot?.paths.contains(where: { $0.id == entry.id }) == true }
    private var storageState: String? {
        if model.snapshot?.pending.contains(entry.id) == true { return "Waiting to move" }
        switch model.snapshot?.paths.first(where: { $0.id == entry.id })?.state {
        case "external": return "On SSD"
        case "local-cache": return "Using a cache on this Mac"
        case "requires-disk": return "Connect SSD to use this folder"
        case "needs-attention": return "Needs attention · see Transfers"
        default: return nil
        }
    }

    var body: some View {
        HStack(spacing: 14) {
            Toggle(isOn: Binding(get: { model.selection.contains(entry.id) }, set: {
                if $0 { model.selection.insert(entry.id) } else { model.selection.remove(entry.id) }
            })) { Text(entry.name) }.labelsHidden()
                .toggleStyle(.checkbox).accessibilityLabel("Select \(entry.name)")
                .disabled(model.isBusy || managed || entry.status != "available")
            VStack(alignment: .leading, spacing: 4) {
                Text(entry.name).font(.headline)
                Text(entry.source).font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                    .help(entry.source).textSelection(.enabled)
                if let reason = entry.reason { Text(reason).font(.caption).foregroundStyle(.orange) }
                else if entry.status == "access-denied" { Text("Access denied — allow folder access in System Settings.").font(.caption).foregroundStyle(.orange) }
                else if entry.status == "linked" && !managed { Text("Already linked — review the existing storage configuration.").font(.caption).foregroundStyle(.orange) }
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 4) {
                Text(storageState ?? entry.allocatedBytes.map(formatBytes) ?? "Size not measured").monospacedDigit()
                Label(entry.kind == "cache" ? "Local cache without SSD" : "Needs SSD connected",
                      systemImage: entry.kind == "cache" ? "internaldrive" : "externaldrive")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.padding(16)
            .background(model.selection.contains(entry.id) && !managed ? Color.teal.opacity(0.05) : .clear)
    }
}
