import SwiftUI

@main
struct CostolaApp: App {
    @StateObject private var model = StorageModel()
    @NSApplicationDelegateAdaptor(CostolaDelegate.self) private var delegate

    var body: some Scene {
        Window("Costola", id: "storage") {
            CostolaRootView().environmentObject(model)
                .onAppear { delegate.model = model }
                .frame(minWidth: 820, minHeight: 570)
        }
        .defaultSize(width: 1040, height: 720)
        MenuBarExtra("Costola", systemImage: "externaldrive") {
            MenuBarView().environmentObject(model)
        }
    }
}

@MainActor
final class CostolaDelegate: NSObject, NSApplicationDelegate {
    weak var model: StorageModel?
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard model?.isMutating == true else { return .terminateNow }
        let alert = NSAlert()
        alert.messageText = "An operation is still running"
        alert.informativeText = "Wait for it to finish before quitting Costola. You can close the window while it runs."
        alert.addButton(withTitle: "Keep Costola open")
        alert.runModal()
        return .terminateCancel
    }
}
