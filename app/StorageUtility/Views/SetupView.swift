import SwiftUI

struct SetupView: View {
    @EnvironmentObject private var model: StorageModel
    @State private var selectedID = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Choose your external SSD", systemImage: "externaldrive.badge.plus").font(.headline)
            Text("Costola uses one APFS or exFAT disk. Existing files on it are kept.").font(.callout).foregroundStyle(.secondary)
            HStack {
                Picker("External disk", selection: $selectedID) {
                    Text("Choose a disk…").tag("")
                    ForEach(model.volumes) { volume in Text("\(volume.name) · \(formatBytes(volume.capacity))").tag(volume.id) }
                }.labelsHidden()
                Button("Use this disk") {
                    if let volume = model.volumes.first(where: { $0.id == selectedID }) { Task { await model.chooseDisk(volume) } }
                }.disabled(selectedID.isEmpty || model.isBusy || model.snapshot?.legacyConflict == true)
            }
            if model.volumes.isEmpty { Text("Connect a compatible external disk, then refresh.").font(.caption).foregroundStyle(.secondary) }
        }.padding(20).background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }
}

struct MigrationPreviewView: View {
    let preview: MigrationPreview
    @EnvironmentObject private var model: StorageModel

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Review your migration").font(.title.weight(.semibold))
            HStack(spacing: 26) {
                metric("To copy", preview.logicalBytes)
                metric("Estimated space reclaimed", preview.estimatedReclaimableBytes)
                metric("External space needed", preview.requiredBytes)
            }
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(preview.entries) { entry in
                        HStack {
                            Text(entry.name)
                            Spacer()
                            Text(entry.kind == "cache" ? "Local cache offline" : "SSD required").foregroundStyle(.secondary)
                        }
                    }
                }
            }.frame(maxHeight: 210)
            Text(preview.note).font(.caption).foregroundStyle(.secondary)
            if preview.preliminary {
                Text("Final space checks run after preparing the disk, before any folders are moved.").font(.callout).foregroundStyle(.secondary)
            }
            ForEach(preview.blockers, id: \.self) { Text($0).foregroundStyle(.orange) }
            HStack {
                Button("Back") { model.preview = nil }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Move selected folders") { Task { await model.confirmMigration() } }
                    .buttonStyle(.borderedProminent).disabled(!preview.ready || model.isBusy).keyboardShortcut(.defaultAction)
            }
        }.padding(28).frame(width: 600)
    }

    private func metric(_ label: String, _ bytes: Int64) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(formatBytes(bytes)).font(.title2.monospacedDigit())
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
    }
}
