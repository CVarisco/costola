import SwiftUI

struct SetupView: View {
    @EnvironmentObject private var model: StorageModel
    @State private var selectedID = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Choose your external SSD", systemImage: "externaldrive.badge.plus").font(.title3.weight(.semibold))
            Text("Use an external SSD formatted as APFS or exFAT. Costola keeps the files already on it and does not format it.").font(.callout).foregroundStyle(.secondary)
            HStack {
                Picker("External disk", selection: $selectedID) {
                    Text("Choose a disk…").tag("")
                    ForEach(model.volumes) { volume in Text("\(volume.name) · \(formatBytes(volume.capacity))").tag(volume.id) }
                }.labelsHidden().accessibilityLabel("External disk").frame(maxWidth: .infinity)
                Button("Use this disk") {
                    if let volume = model.volumes.first(where: { $0.id == selectedID }) { Task { await model.chooseDisk(volume) } }
                }.disabled(!model.volumes.contains(where: { $0.id == selectedID }) || model.isBusy || model.snapshot?.legacyConflict == true)
            }
            if let volume = model.volumes.first(where: { $0.id == selectedID }) {
                Text("\(volume.filesystem.uppercased()) · \(formatBytes(volume.capacity)) total capacity. Choosing a disk does not move your folders.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if model.volumes.isEmpty {
                HStack {
                    Text("No compatible disk found. Connect an APFS or exFAT disk.").font(.callout).foregroundStyle(.secondary)
                    Spacer()
                    Button("Look for disks") { Task { await model.refresh() } }.disabled(model.isBusy || model.isLoading)
                }
            }
        }.padding(20).background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }
}

struct MigrationPreviewView: View {
    let preview: MigrationPreview
    @EnvironmentObject private var model: StorageModel

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Before you move these folders").font(.title.weight(.semibold))
            Text("\(preview.entries.count) \(preview.entries.count == 1 ? "folder" : "folders") → \(model.snapshot?.device?.name ?? "external SSD")")
                .foregroundStyle(.secondary)
            HStack(spacing: 26) {
                metric("Data to copy", preview.logicalBytes)
                metric("Estimated space freed on Mac", preview.estimatedReclaimableBytes)
                metric("Space needed on SSD", preview.requiredBytes)
            }
            Text("The SSD estimate includes a 1 GiB safety margin. Existing destination files may need extra space.")
                .font(.caption).foregroundStyle(.secondary)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(preview.entries) { entry in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(entry.name).font(.headline)
                                Text(entry.source).font(.caption).foregroundStyle(.secondary)
                                    .lineLimit(1).truncationMode(.middle).help(entry.source)
                            }
                            Spacer()
                            Label(entry.kind == "cache" ? "Local cache without SSD" : "Needs SSD connected",
                                  systemImage: entry.kind == "cache" ? "internaldrive" : "externaldrive")
                                .font(.callout).foregroundStyle(.secondary)
                        }
                    }
                }
            }.frame(maxHeight: 210)
            Label("Close apps and tools using these folders before moving them.", systemImage: "pause.circle")
                .font(.callout)
            if preview.entries.contains(where: { $0.kind != "cache" }) {
                Label("You will need the SSD connected to use the SDKs and personal folders you move.", systemImage: "externaldrive.badge.exclamationmark")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Text(preview.note).font(.caption).foregroundStyle(.secondary)
            if preview.preliminary {
                Text("This is a first estimate. Costola checks the available space again after preparing the SSD, before moving folders.").font(.callout).foregroundStyle(.secondary)
            }
            ForEach(preview.blockers, id: \.self) {
                Label($0, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange).textSelection(.enabled)
            }
            HStack {
                Button("Back") { model.preview = nil }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Move selected folders") { Task { await model.confirmMigration() } }
                    .buttonStyle(.borderedProminent).disabled(!preview.ready || model.isBusy).keyboardShortcut(.defaultAction)
            }
        }.padding(28).frame(width: 640)
            .interactiveDismissDisabled(model.isBusy)
            .tint(.teal)
    }

    private func metric(_ label: String, _ bytes: Int64) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(formatBytes(bytes)).font(.title2.monospacedDigit())
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
    }
}
