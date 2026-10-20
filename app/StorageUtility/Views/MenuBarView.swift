import SwiftUI

struct MenuBarView: View {
    @EnvironmentObject private var model: StorageModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Text(model.isBusy ? model.phase : model.snapshot?.online == true ? "SSD storage ready" : "SSD storage unavailable")
        Button("Open Costola") { show(.storage) }
        Button("Transfers & recovery") { show(.operations) }
        Button("Refresh status") { Task { await model.refresh(includeCatalog: false) } }.disabled(model.isBusy)
        Divider()
        Button("Quit Costola") { NSApplication.shared.terminate(nil) }.keyboardShortcut("q")
    }

    private func show(_ section: AppSection) {
        model.section = section
        openWindow(id: "storage")
        NSApplication.shared.activate(ignoringOtherApps: true)
    }
}
