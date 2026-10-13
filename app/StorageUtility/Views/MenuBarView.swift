import SwiftUI

struct MenuBarView: View {
    @EnvironmentObject private var model: StorageModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Text(model.isBusy ? model.phase : model.snapshot?.online == true ? "External storage available" : "External storage not mounted")
        Button("Open Costola") { show(.storage) }
        Button("Operations and recovery") { show(.operations) }
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
