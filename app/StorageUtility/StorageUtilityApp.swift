import SwiftUI

@main
struct CostolaApp: App {
    var body: some Scene {
        WindowGroup("Costola", id: "storage") {
            BundleCheckView()
                .frame(minWidth: 560, minHeight: 360)
        }
        MenuBarExtra("Costola", systemImage: "externaldrive") {
            OpenCostolaButton()
            Divider()
            Button("Quit Costola") { NSApplication.shared.terminate(nil) }
                .keyboardShortcut("q")
        }
    }
}

private struct OpenCostolaButton: View {
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Button("Open Costola") {
            openWindow(id: "storage")
            NSApplication.shared.activate(ignoringOtherApps: true)
        }
    }
}

private struct BundleCheckView: View {
    @State private var result = "Checking the bundled engine…"
    @State private var ready = false
    @State private var checking = true

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Label("Costola", systemImage: "externaldrive.fill")
                .font(.largeTitle.weight(.semibold))
            Text("More room for your work.")
                .font(.title2).foregroundStyle(.secondary)
            Divider()
            Label(result, systemImage: checking ? "hourglass" : (ready ? "checkmark.circle" : "exclamationmark.triangle"))
                .textSelection(.enabled)
            Text("Development build · Storage setup is not available yet.")
                .font(.callout).foregroundStyle(.secondary)
            Spacer()
        }
        .padding(32)
        .task {
            let appURL = Bundle.main.bundleURL
            do {
                let response = try await Task.detached {
                    try BundleWorker.probe(appURL: appURL).0
                }.value
                result = "Engine ready · \(response.data!.architecture) · Python \(response.data!.pythonVersion)"
                ready = true
            } catch {
                result = error.localizedDescription
            }
            checking = false
        }
    }
}
